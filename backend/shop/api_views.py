import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError as DRFValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from django.core.exceptions import ValidationError as DjangoValidationError
from points.services import InsufficientPointsError, PointService
from rbac.models import Role
from rbac.services import get_user_role_codes, has_user_permission
from .inventory_service import InventoryService
from .models import Category, InventoryTransaction, Order, OrderItem, Product, ProductInventory
from .permissions import (
    CanAdjustInventory,
    CanCancelOrder,
    CanCreateOrder,
    CanCreateProduct,
    CanDeleteProduct,
    CanUpdateProduct,
    CanUpdateSellerOrder,
    CanViewInventory,
    CanViewOrder,
    CanViewSellerOrder,
    IsEligibleOrderSeller,
    IsEligibleProductSeller,
    IsInventoryProductOwner,
    IsOrderOwner,
    IsProductOwner,
)
from .serializers import (
    CategorySerializer,
    InventoryAdjustmentSerializer,
    InventoryTransactionSerializer,
    OrderCancelSerializer,
    OrderCreateSerializer,
    OrderDetailSerializer,
    ProductDetailSerializer,
    ProductInventorySerializer,
    ProductListSerializer,
    SellerOrderDetailSerializer,
    SellerOrderItemSerializer,
    SellerOrderListSerializer,
    SellerOrderStatusUpdateSerializer,
    SellerProductCreateSerializer,
    SellerProductSerializer,
    SellerProductUpdateSerializer,
)
from .services import IneligibleSellerError, OrderService, ProductOwnershipError, ProductService



class StandardResultsSetPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 100


class CategoryListView(generics.ListAPIView):
    """
    Public listing of active categories.
    Annotates products_count based strictly on publicly visible products.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CategorySerializer
    pagination_class = None

    def get_queryset(self):
        return ProductService.get_public_categories_queryset()


class ProductListAPIView(generics.ListAPIView):
    """
    Public catalog product listing.
    Enforces strict database-level public visibility:
      - Product is active and published
      - Category is active
      - Shop is approved/active
      - Seller is operational
    Supports filtering by category, shop, price range, badge, search, and sorting.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ProductListSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = ProductService.get_public_products_queryset()

        # Filter by category slug
        category_slug = self.request.query_params.get("category")
        if category_slug and category_slug.lower() != "all":
            queryset = queryset.filter(category__slug=category_slug)

        # Filter by shop (ID or slug)
        shop_param = self.request.query_params.get("shop")
        if shop_param:
            shop_str = str(shop_param).strip()
            if shop_str.isdigit():
                queryset = queryset.filter(shop_id=int(shop_str))
            else:
                queryset = queryset.filter(shop__slug=shop_str)

        # Filter by minimum price
        min_price = self.request.query_params.get("min_price")
        if min_price is not None and min_price != "":
            try:
                min_val = Decimal(min_price)
                if min_val >= 0:
                    queryset = queryset.filter(price__gte=min_val)
            except Exception:
                pass

        # Filter by maximum price
        max_price = self.request.query_params.get("max_price")
        if max_price is not None and max_price != "":
            try:
                max_val = Decimal(max_price)
                if max_val >= 0:
                    queryset = queryset.filter(price__lte=max_val)
            except Exception:
                pass

        # Filter by badge
        badge = self.request.query_params.get("badge")
        if badge:
            queryset = queryset.filter(badge__iexact=badge.strip())

        # Search filter (name, description, category name)
        search_query = self.request.query_params.get("q") or self.request.query_params.get("search")
        if search_query:
            term = search_query.strip()
            queryset = queryset.filter(
                Q(name__icontains=term)
                | Q(description__icontains=term)
                | Q(category__name__icontains=term)
            ).distinct()

        # Ordering
        ordering = self.request.query_params.get("ordering")
        ORDERING_MAP = {
            "newest": "-created_at",
            "-created_at": "-created_at",
            "created_at": "created_at",
            "oldest": "created_at",
            "price": "price",
            "price_asc": "price",
            "-price": "-price",
            "price_desc": "-price",
            "name": "name",
            "name_asc": "name",
            "-name": "-name",
            "name_desc": "-name",
        }
        if ordering and ordering in ORDERING_MAP:
            queryset = queryset.order_by(ORDERING_MAP[ordering])
        else:
            queryset = queryset.order_by("-created_at")

        return queryset


class ProductDetailAPIView(generics.RetrieveAPIView):
    """
    Public product detail endpoint.
    Supports lookup by either primary key (ID) or slug:
      - /api/products/<int:pk>/
      - /api/products/<slug:slug>/
    Enforces strict database-level public visibility.
    Non-public, draft, rejected, or suspended-shop products return HTTP 404.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ProductDetailSerializer

    def get_object(self):
        pk = self.kwargs.get("pk")
        slug = self.kwargs.get("slug")
        identifier = pk if pk is not None else slug
        return ProductService.get_public_product_by_identifier(identifier)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        # Add related public products in the same category
        related_products = (
            ProductService.get_public_products_queryset()
            .filter(category=instance.category)
            .exclude(id=instance.id)[:4]
        )
        data["related_products"] = ProductListSerializer(
            related_products, many=True, context={"request": request}
        ).data

        return Response(data)


class HotDealAPIView(APIView):
    """
    Public endpoint returning the most featured/discounted deal product.
    Only publicly visible products are eligible.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        public_qs = ProductService.get_public_products_queryset()
        deal_product = (
            public_qs.filter(old_price__isnull=False)
            .exclude(old_price__lte=0)
            .order_by("-created_at")
            .first()
        )

        if not deal_product:
            deal_product = public_qs.order_by("-created_at").first()

        if not deal_product:
            return Response({"detail": "No hot deal available."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProductListSerializer(deal_product, context={"request": request})
        data = serializer.data
        data["deal_ends_in_hours"] = 72  # Countdown reference anchor

        return Response(data)


class OrderListCreateAPIView(APIView):
    """
    Customer Order API:
      GET: Lists authenticated customer's orders with pagination.
      POST: Converts the authenticated customer's Cart into a persistent Order snapshot.
    """
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), CanCreateOrder()]
        return [permissions.IsAuthenticated(), CanViewOrder()]

    def get(self, request):
        queryset = (
            Order.objects.filter(user=request.user)
            .prefetch_related(
                "items",
                "items__product",
                "items__shop",
                "items__seller",
            )
            .order_by("-created_at")
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = OrderDetailSerializer(page, many=True, context={"request": request})
            return paginator.get_paginated_response(serializer.data)

        serializer = OrderDetailSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        # Extract client IP for audit recording
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        ip_address = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR")

        try:
            order = OrderService.create_order_from_cart(
                user=request.user,
                address_id=validated_data.get("address_id"),
                address_data=validated_data,
                actor=request.user,
                ip_address=ip_address,
            )
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages})

        detail_serializer = OrderDetailSerializer(order, context={"request": request})
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)


# Backwards-compatibility alias
OrderCreateAPIView = OrderListCreateAPIView


class OrderDetailAPIView(APIView):
    """
    Customer Order Detail API:
      GET: Retrieves an order by ID or order_number.
      Enforces strict customer ownership isolation (User B receives 404 for User A's order).
    """
    permission_classes = [permissions.IsAuthenticated, CanViewOrder]

    def get(self, request, *args, **kwargs):
        lookup = (
            kwargs.get("order_number")
            or kwargs.get("pk")
            or kwargs.get("identifier")
            or request.query_params.get("order_number")
        )
        if not lookup:
            raise NotFound("Order reference missing.")

        lookup_str = str(lookup).strip()
        qs = Order.objects.prefetch_related(
            "items",
            "items__product",
            "items__shop",
            "items__seller",
        )

        if lookup_str.isdigit():
            order = qs.filter(id=int(lookup_str)).first()
        else:
            order = qs.filter(order_number=lookup_str).first()

        if not order:
            raise NotFound("Order not found.")

        # Strict customer ownership isolation
        user = request.user
        role_codes = get_user_role_codes(user)
        is_staff_override = (
            user.is_superuser
            or user.is_staff
            or Role.ROLE_SUPER_ADMINISTRATOR in role_codes
            or Role.ROLE_ADMINISTRATOR in role_codes
            or Role.ROLE_OPERATION_MANAGER in role_codes
        )
        if order.user != user and not is_staff_override:
            raise NotFound("Order not found.")

        serializer = OrderDetailSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrderCancelAPIView(APIView):
    """
    Customer Order Cancellation API:
      PATCH /api/orders/<order_number>/cancel/
      POST  /api/orders/<order_number>/cancel/
      PATCH /api/orders/<id>/cancel/
      POST  /api/orders/<id>/cancel/

    Allows authenticated customers to cancel eligible orders (PENDING, CONFIRMED, PROCESSING).
    Rejects arbitrary status manipulations.
    Atomically releases inventory reservations and writes immutable audit entries.
    Returns safe 404 for orders belonging to other customers.
    """
    permission_classes = [permissions.IsAuthenticated, CanCancelOrder]

    def patch(self, request, *args, **kwargs):
        return self._handle_cancellation(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self._handle_cancellation(request, *args, **kwargs)

    def _handle_cancellation(self, request, *args, **kwargs):
        lookup = (
            kwargs.get("order_number")
            or kwargs.get("pk")
            or kwargs.get("identifier")
            or request.query_params.get("order_number")
        )
        if not lookup:
            raise NotFound("Order reference missing.")

        lookup_str = str(lookup).strip()
        qs = Order.objects.prefetch_related(
            "items",
            "items__product",
            "items__shop",
            "items__seller",
        )

        if lookup_str.isdigit():
            order = qs.filter(id=int(lookup_str)).first()
        else:
            order = qs.filter(order_number=lookup_str).first()

        if not order:
            raise NotFound("Order not found.")

        # Strict customer ownership isolation (User B receives safe 404 for User A's order)
        user = request.user
        role_codes = get_user_role_codes(user)
        is_staff_override = (
            user.is_superuser
            or user.is_staff
            or Role.ROLE_SUPER_ADMINISTRATOR in role_codes
            or Role.ROLE_ADMINISTRATOR in role_codes
            or Role.ROLE_OPERATION_MANAGER in role_codes
        )
        if order.user != user and not is_staff_override:
            raise NotFound("Order not found.")

        serializer = OrderCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")

        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        ip_address = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR")

        try:
            cancelled_order = OrderService.cancel_customer_order(
                order=order,
                customer=request.user,
                reason=reason,
                ip_address=ip_address,
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
            return Response(detail, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        detail_serializer = OrderDetailSerializer(cancelled_order, context={"request": request})
        return Response(detail_serializer.data, status=status.HTTP_200_OK)


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


# ---------------------------------------------------------------------------
# Seller Order Management APIs
# ---------------------------------------------------------------------------

class SellerOrderListAPIView(APIView):
    """
    Seller-specific order listing endpoint:
      GET /api/seller/orders/
      Returns orders containing items belonging to the authenticated seller.
      Each order's items list contains only that seller's items.
    """
    pagination_class = StandardResultsSetPagination
    permission_classes = [permissions.IsAuthenticated, IsEligibleOrderSeller, CanViewSellerOrder]

    def get(self, request):
        seller = request.user.seller_profile
        queryset = OrderService.get_seller_orders_queryset(seller)

        status_param = request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status__iexact=status_param.strip())

        search_query = request.query_params.get("q") or request.query_params.get("search")
        if search_query:
            query = search_query.strip()
            queryset = queryset.filter(
                Q(order_number__icontains=query)
                | Q(shipping_recipient_name__icontains=query)
                | Q(customer_name__icontains=query)
            )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = SellerOrderListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class SellerOrderDetailAPIView(APIView):
    """
    Seller-specific order detail endpoint:
      GET /api/seller/orders/<order_number>/
      Retrieves order details for fulfillment.
      Enforces that the order contains items belonging to the authenticated seller.
      Excludes another seller's items and private customer credentials.
    """
    permission_classes = [permissions.IsAuthenticated, IsEligibleOrderSeller, CanViewSellerOrder]

    def get(self, request, order_number=None, *args, **kwargs):
        seller = request.user.seller_profile
        lookup = order_number or kwargs.get("order_number") or kwargs.get("pk") or request.query_params.get("order_number")
        if not lookup:
            raise NotFound("Order reference missing.")

        order = OrderService.get_seller_order(lookup, seller)
        serializer = SellerOrderDetailSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class SellerOrderStatusUpdateAPIView(APIView):
    """
    Seller order status transition endpoint:
      PATCH /api/seller/orders/<order_number>/status/
      Safely advances an order's lifecycle status.
      Rejects unilateral transitions on multi-seller orders.
    """
    permission_classes = [permissions.IsAuthenticated, IsEligibleOrderSeller, CanUpdateSellerOrder]

    def patch(self, request, order_number=None, *args, **kwargs):
        seller = request.user.seller_profile
        lookup = order_number or kwargs.get("order_number") or kwargs.get("pk")
        if not lookup:
            raise NotFound("Order reference missing.")

        order = OrderService.get_seller_order(lookup, seller)
        serializer = SellerOrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        note = serializer.validated_data.get("note", "")
        ip_address = request.META.get("REMOTE_ADDR")

        try:
            updated_order = OrderService.transition_seller_order_status(
                order=order,
                new_status=new_status,
                seller=seller,
                actor=request.user,
                note=note,
                ip_address=ip_address,
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
            return Response(detail, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        detail_serializer = SellerOrderDetailSerializer(updated_order, context={"request": request})
        return Response(detail_serializer.data, status=status.HTTP_200_OK)


class SellerInventoryDetailAPIView(APIView):
    """
    GET /api/seller/inventory/<product_id>/
    GET /api/inventory/<product_id>/
    Retrieves the authoritative inventory record for a product.
    Enforces that caller is an operational seller owning the product (or staff with inventory.view).
    """
    permission_classes = [permissions.IsAuthenticated, CanViewInventory]

    def get(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)

        # Check ownership or staff permission via RBAC
        role_codes = get_user_role_codes(request.user)
        is_staff_override = (
            request.user.is_superuser
            or request.user.is_staff
            or Role.ROLE_SUPER_ADMINISTRATOR in role_codes
            or Role.ROLE_ADMINISTRATOR in role_codes
            or Role.ROLE_OPERATION_MANAGER in role_codes
        )

        if not is_staff_override:
            if not hasattr(request.user, "seller_profile"):
                raise PermissionDenied("You do not have a registered seller profile.")
            seller = request.user.seller_profile
            if not seller.is_operational:
                raise PermissionDenied("Your seller account is not operational.")
            if not (product.shop and product.shop.owner == seller):
                raise PermissionDenied("You do not own the product associated with this inventory.")

        inventory = InventoryService.get_or_create_inventory(product)
        serializer = ProductInventorySerializer(inventory)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SellerInventoryAdjustAPIView(APIView):
    """
    POST /api/seller/inventory/<product_id>/adjust/
    POST /api/inventory/<product_id>/adjust/
    PATCH /api/seller/inventory/<product_id>/
    PATCH /api/inventory/<product_id>/
    Adjusts available stock for a product by delta quantity (+/-).
    Enforces that caller is an operational seller owning the product (or staff with inventory.adjust).
    """
    permission_classes = [permissions.IsAuthenticated, CanAdjustInventory]

    def post(self, request, product_id):
        return self._handle_adjustment(request, product_id)

    def patch(self, request, product_id):
        return self._handle_adjustment(request, product_id)

    def _handle_adjustment(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)

        # Check ownership or staff permission via RBAC
        role_codes = get_user_role_codes(request.user)
        is_staff_override = (
            request.user.is_superuser
            or request.user.is_staff
            or Role.ROLE_SUPER_ADMINISTRATOR in role_codes
            or Role.ROLE_ADMINISTRATOR in role_codes
            or Role.ROLE_OPERATION_MANAGER in role_codes
        )

        if not is_staff_override:
            if not hasattr(request.user, "seller_profile"):
                raise PermissionDenied("You do not have a registered seller profile.")
            seller = request.user.seller_profile
            if not seller.is_operational:
                raise PermissionDenied("Your seller account is not operational.")
            if not (product.shop and product.shop.owner == seller):
                raise PermissionDenied("You do not own the product associated with this inventory.")

        serializer = InventoryAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        quantity_delta = serializer.validated_data["quantity"]
        reason = serializer.validated_data.get("reason", "")
        ip_address = request.META.get("REMOTE_ADDR")

        try:
            inventory = InventoryService.adjust_stock(
                product=product,
                quantity_delta=quantity_delta,
                actor=request.user,
                reason=reason,
                ip_address=ip_address,
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
            return Response(detail, status=status.HTTP_400_BAD_REQUEST)

        return Response(ProductInventorySerializer(inventory).data, status=status.HTTP_200_OK)


class SellerInventoryListAPIView(generics.ListAPIView):
    """
    GET /api/seller/inventory/
    GET /api/inventory/
    Lists inventory records for products belonging to the authenticated seller (or all for staff).
    """
    permission_classes = [permissions.IsAuthenticated, CanViewInventory]
    serializer_class = ProductInventorySerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        role_codes = get_user_role_codes(user)
        is_staff_override = (
            user.is_superuser
            or user.is_staff
            or Role.ROLE_SUPER_ADMINISTRATOR in role_codes
            or Role.ROLE_ADMINISTRATOR in role_codes
            or Role.ROLE_OPERATION_MANAGER in role_codes
        )

        if is_staff_override:
            return ProductInventory.objects.select_related("product").order_by("-updated_at")

        if not hasattr(user, "seller_profile"):
            raise PermissionDenied("You do not have a registered seller profile.")
        seller = user.seller_profile
        if not seller.is_operational:
            raise PermissionDenied("Your seller account is not operational.")

        return ProductInventory.objects.filter(
            product__shop__owner=seller
        ).select_related("product").order_by("-updated_at")


class SellerInventoryTransactionsAPIView(generics.ListAPIView):
    """
    GET /api/seller/inventory/<product_id>/transactions/
    GET /api/inventory/<product_id>/transactions/
    Retrieves the immutable transaction history for a product.
    """
    permission_classes = [permissions.IsAuthenticated, CanViewInventory]
    serializer_class = InventoryTransactionSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        product_id = self.kwargs.get("product_id")
        product = get_object_or_404(Product, pk=product_id)
        user = self.request.user

        role_codes = get_user_role_codes(user)
        is_staff_override = (
            user.is_superuser
            or user.is_staff
            or Role.ROLE_SUPER_ADMINISTRATOR in role_codes
            or Role.ROLE_ADMINISTRATOR in role_codes
            or Role.ROLE_OPERATION_MANAGER in role_codes
        )

        if not is_staff_override:
            if not hasattr(user, "seller_profile"):
                raise PermissionDenied("You do not have a registered seller profile.")
            seller = user.seller_profile
            if not seller.is_operational:
                raise PermissionDenied("Your seller account is not operational.")
            if not (product.shop and product.shop.owner == seller):
                raise PermissionDenied("You do not own the product associated with this inventory.")

        return InventoryTransaction.objects.filter(product=product).order_by("-created_at")




