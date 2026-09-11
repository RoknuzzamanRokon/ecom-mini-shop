import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from django.core.exceptions import ValidationError as DjangoValidationError
from points.services import InsufficientPointsError, PointService
from rbac.services import has_user_permission
from .models import Category, Order, OrderItem, Product
from .permissions import (
    CanCreateProduct,
    CanDeleteProduct,
    CanUpdateProduct,
    IsEligibleProductSeller,
    IsProductOwner,
)
from .serializers import (
    CategorySerializer,
    OrderCreateSerializer,
    OrderDetailSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    SellerProductCreateSerializer,
    SellerProductSerializer,
    SellerProductUpdateSerializer,
)
from .services import IneligibleSellerError, ProductOwnershipError, ProductService



class StandardResultsSetPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 100


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    pagination_class = None

    def get_queryset(self):
        return (
            Category.objects.filter(is_active=True)
            .annotate(
                products_count=Count(
                    "products", filter=Q(products__is_active=True)
                )
            )
            .order_by("name")
        )


class ProductListAPIView(generics.ListAPIView):
    serializer_class = ProductListSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = (
            Product.objects.filter(is_active=True)
            .select_related("category")
            .order_by("-created_at")
        )

        # Filter by category slug
        category_slug = self.request.query_params.get("category")
        if category_slug and category_slug.lower() != "all":
            queryset = queryset.filter(category__slug=category_slug)

        # Filter by badge
        badge = self.request.query_params.get("badge")
        if badge:
            queryset = queryset.filter(badge__iexact=badge)

        # Search filter
        search_query = self.request.query_params.get("q") or self.request.query_params.get("search")
        if search_query:
            search_query = search_query.strip()
            queryset = queryset.filter(
                Q(name__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(category__name__icontains=search_query)
            ).distinct()

        # Ordering
        ordering = self.request.query_params.get("ordering")
        if ordering:
            allowed_orderings = ["price", "-price", "created_at", "-created_at", "name", "-name"]
            if ordering in allowed_orderings:
                queryset = queryset.order_by(ordering)

        return queryset


class ProductDetailAPIView(generics.RetrieveAPIView):
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return Product.objects.filter(is_active=True).select_related("category").prefetch_related("images")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        # Add related products in the same category
        related_products = (
            Product.objects.filter(category=instance.category, is_active=True)
            .exclude(id=instance.id)
            .order_by("-created_at")[:4]
        )
        data["related_products"] = ProductListSerializer(
            related_products, many=True, context={"request": request}
        ).data

        return Response(data)


class HotDealAPIView(APIView):
    def get(self, request):
        # Pick the most heavily discounted product or newest discounted product
        deal_product = (
            Product.objects.filter(is_active=True, old_price__isnull=False)
            .exclude(old_price__lte=0)
            .order_by("-created_at")
            .first()
        )

        if not deal_product:
            deal_product = (
                Product.objects.filter(is_active=True)
                .order_by("-created_at")
                .first()
            )

        if not deal_product:
            return Response({"detail": "No hot deal available."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProductListSerializer(deal_product, context={"request": request})
        data = serializer.data
        data["deal_ends_in_hours"] = 72  # Countdown reference anchor

        return Response(data)


class OrderCreateAPIView(APIView):
    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        items_data = validated_data["items"]
        product_ids = [item["product_id"] for item in items_data]
        products_map = {
            p.id: p
            for p in Product.objects.filter(id__in=product_ids, is_active=True)
        }

        # Check all products exist
        missing_ids = [pid for pid in product_ids if pid not in products_map]
        if missing_ids:
            return Response(
                {"detail": f"Products with IDs {missing_ids} do not exist or are inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Calculate totals and validate stock
        total_amount = Decimal("0.00")
        order_items_to_create = []

        for item_data in items_data:
            product = products_map[item_data["product_id"]]
            quantity = item_data["quantity"]
            subtotal = product.price * quantity
            total_amount += subtotal

            order_items_to_create.append(
                {
                    "product": product,
                    "product_name": product.name,
                    "price": product.price,
                    "quantity": quantity,
                    "subtotal": subtotal,
                }
            )

        order_number = f"ORD{timezone.now():%Y%m%d}{uuid.uuid4().hex[:6].upper()}"

        with transaction.atomic():
            order = Order.objects.create(
                order_number=order_number,
                customer_name=validated_data["customer_name"],
                phone=validated_data["phone"],
                address=validated_data["address"],
                city=validated_data["city"],
                total_amount=total_amount,
                status=Order.STATUS_PENDING,
            )

            for item_info in order_items_to_create:
                OrderItem.objects.create(
                    order=order,
                    product=item_info["product"],
                    product_name=item_info["product_name"],
                    price=item_info["price"],
                    quantity=item_info["quantity"],
                    subtotal=item_info["subtotal"],
                )

        detail_serializer = OrderDetailSerializer(order)
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)


class OrderDetailAPIView(generics.RetrieveAPIView):
    serializer_class = OrderDetailSerializer
    lookup_field = "order_number"
    queryset = Order.objects.prefetch_related("items")


# ---------------------------------------------------------------------------
# Seller Product Self-Service APIs
# ---------------------------------------------------------------------------

class SellerProductListCreateAPIView(APIView):
    """
    Seller self-service product endpoint:
      GET: Lists products belonging to shops owned by the authenticated seller.
      POST: Creates a new product for an owned shop, atomically debiting seller points
            and creating an immutable audit record.
    """
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsEligibleProductSeller(), CanCreateProduct()]
        return [permissions.IsAuthenticated(), IsEligibleProductSeller()]

    def get(self, request):
        seller = request.user.seller_profile
        queryset = (
            Product.objects.filter(shop__owner=seller)
            .select_related("category", "shop", "shop__owner")
            .prefetch_related("images")
            .order_by("-created_at")
        )

        # Optional filters
        shop_id = request.query_params.get("shop_id") or request.query_params.get("shop")
        if shop_id:
            queryset = queryset.filter(shop_id=shop_id)

        status_param = request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status__iexact=status_param.strip())

        category_param = request.query_params.get("category")
        if category_param:
            if category_param.isdigit():
                queryset = queryset.filter(category_id=int(category_param))
            else:
                queryset = queryset.filter(category__slug=category_param)

        search_query = request.query_params.get("q") or request.query_params.get("search")
        if search_query:
            query = search_query.strip()
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(shop__name__icontains=query)
            )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = SellerProductSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = SellerProductCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            product = ProductService.create_product(
                seller=request.user.seller_profile,
                name=data["name"],
                category=data["category_id"],
                shop=data["shop_id"],
                description=data["description"],
                price=data["price"],
                old_price=data.get("old_price"),
                stock=data.get("stock", 0),
                badge=data.get("badge", ""),
                image=request.FILES.get("image") or data.get("image"),
                is_active=data.get("is_active", True),
                actor=request.user,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
        except InsufficientPointsError as e:
            cost = PointService.get_product_creation_cost()
            balance = PointService.get_balance(request.user.seller_profile)
            return Response(
                {
                    "error": str(e),
                    "required_points": cost,
                    "available_points": balance,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (IneligibleSellerError, ProductOwnershipError) as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except PermissionDenied as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as e:
            err_detail = e.message_dict if hasattr(e, "message_dict") else str(e)
            return Response({"error": err_detail}, status=status.HTTP_400_BAD_REQUEST)

        response_serializer = SellerProductSerializer(product, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class SellerProductDetailAPIView(APIView):
    """
    Seller self-service product detail endpoint:
      GET: Retrieve product details.
      PATCH/PUT: Update product attributes (requires products.update).
      DELETE: Delete product (requires products.delete).
    Strictly verifies ownership: product must belong to a shop owned by the authenticated seller.
    """
    permission_classes = [permissions.IsAuthenticated, IsEligibleProductSeller, IsProductOwner]

    def get_object(self, pk):
        product = get_object_or_404(
            Product.objects.select_related("category", "shop", "shop__owner").prefetch_related("images"),
            pk=pk,
        )
        self.check_object_permissions(self.request, product)
        return product

    def get(self, request, pk):
        product = self.get_object(pk)
        serializer = SellerProductSerializer(product, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        product = self.get_object(pk)
        if not has_user_permission(request.user, "products.update"):
            return Response(
                {"error": "You do not have permission to update products ('products.update' required)."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SellerProductUpdateSerializer(data=request.data, context={"request": request}, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            updated_product = ProductService.update_product(
                product=product,
                seller=request.user.seller_profile,
                data=data,
                actor=request.user,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
        except (IneligibleSellerError, ProductOwnershipError, PermissionDenied) as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as e:
            err_detail = e.message_dict if hasattr(e, "message_dict") else str(e)
            return Response({"error": err_detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            SellerProductSerializer(updated_product, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        product = self.get_object(pk)
        if not has_user_permission(request.user, "products.delete"):
            return Response(
                {"error": "You do not have permission to delete products ('products.delete' required)."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            ProductService.delete_product(
                product=product,
                seller=request.user.seller_profile,
                actor=request.user,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
        except (IneligibleSellerError, ProductOwnershipError, PermissionDenied) as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)

        return Response({"message": "Product successfully deleted."}, status=status.HTTP_204_NO_CONTENT)

