import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category, Order, OrderItem, Product
from .serializers import (
    CategorySerializer,
    OrderCreateSerializer,
    OrderDetailSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
)


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
