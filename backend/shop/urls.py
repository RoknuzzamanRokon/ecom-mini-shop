from django.urls import path

from . import api_views, views

app_name = "shop"

urlpatterns = [
    # Traditional Django template views
    path("", views.product_list, name="product_list"),
    path("category/<slug:category_slug>/", views.product_list, name="category"),
    path("product/<slug:slug>/", views.product_detail, name="product_detail"),
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/<int:product_id>/", views.cart_add, name="cart_add"),
    path("cart/increase/<int:product_id>/", views.cart_increase, name="cart_increase"),
    path("cart/decrease/<int:product_id>/", views.cart_decrease, name="cart_decrease"),
    path("cart/remove/<int:product_id>/", views.cart_remove, name="cart_remove"),
    path("checkout/", views.checkout, name="checkout"),
    path("order-success/<int:order_id>/", views.order_success, name="order_success"),

    # REST API endpoints for Next.js frontend
    path("api/categories/", api_views.CategoryListView.as_view(), name="api_categories"),
    path("api/products/mine/", api_views.SellerProductListCreateAPIView.as_view(), name="api_seller_products"),
    path("api/products/mine/<int:pk>/", api_views.SellerProductDetailAPIView.as_view(), name="api_seller_product_detail"),
    path("api/products/", api_views.ProductListAPIView.as_view(), name="api_products"),
    path("api/products/<int:pk>/", api_views.ProductDetailAPIView.as_view(), name="api_product_detail_pk"),
    path("api/products/<slug:slug>/", api_views.ProductDetailAPIView.as_view(), name="api_product_detail"),
    path("api/hot-deals/", api_views.HotDealAPIView.as_view(), name="api_hot_deal"),
    path("api/orders/", api_views.OrderListCreateAPIView.as_view(), name="api_orders"),
    path("api/orders/", api_views.OrderListCreateAPIView.as_view(), name="api_order_create"),
    path("api/orders/<int:pk>/", api_views.OrderDetailAPIView.as_view(), name="api_order_detail_pk"),
    path("api/orders/<str:order_number>/", api_views.OrderDetailAPIView.as_view(), name="api_order_detail"),

    # Seller Order APIs
    path("api/seller/orders/", api_views.SellerOrderListAPIView.as_view(), name="api_seller_orders"),
    path("api/seller/orders/<str:order_number>/", api_views.SellerOrderDetailAPIView.as_view(), name="api_seller_order_detail"),
    path("api/seller/orders/<str:order_number>/status/", api_views.SellerOrderStatusUpdateAPIView.as_view(), name="api_seller_order_status_update"),
]

