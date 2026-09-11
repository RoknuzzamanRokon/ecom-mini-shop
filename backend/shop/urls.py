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
    path("api/orders/<int:pk>/cancel/", api_views.OrderCancelAPIView.as_view(), name="api_order_cancel_pk"),
    path("api/orders/<str:order_number>/cancel/", api_views.OrderCancelAPIView.as_view(), name="api_order_cancel"),

    # Seller Order APIs
    path("api/seller/orders/", api_views.SellerOrderListAPIView.as_view(), name="api_seller_orders"),
    path("api/seller/orders/<str:order_number>/", api_views.SellerOrderDetailAPIView.as_view(), name="api_seller_order_detail"),
    path("api/seller/orders/<str:order_number>/status/", api_views.SellerOrderStatusUpdateAPIView.as_view(), name="api_seller_order_status_update"),

    # Inventory APIs
    path("api/seller/inventory/", api_views.SellerInventoryListAPIView.as_view(), name="api_seller_inventory_list"),
    path("api/seller/inventory/<int:product_id>/", api_views.SellerInventoryDetailAPIView.as_view(), name="api_seller_inventory_detail"),
    path("api/seller/inventory/<int:product_id>/adjust/", api_views.SellerInventoryAdjustAPIView.as_view(), name="api_seller_inventory_adjust"),
    path("api/seller/inventory/<int:product_id>/transactions/", api_views.SellerInventoryTransactionsAPIView.as_view(), name="api_seller_inventory_transactions"),
    path("api/inventory/", api_views.SellerInventoryListAPIView.as_view(), name="api_inventory_list"),
    path("api/inventory/<int:product_id>/", api_views.SellerInventoryDetailAPIView.as_view(), name="api_inventory_detail"),
    # Payment & Refund APIs (Task 15)
    path("api/orders/<int:pk>/payment/", api_views.CustomerOrderPaymentAPIView.as_view(), name="api_order_payment_pk"),
    path("api/orders/<str:order_number>/payment/", api_views.CustomerOrderPaymentAPIView.as_view(), name="api_order_payment"),
    path("api/staff/payments/", api_views.StaffPaymentListAPIView.as_view(), name="api_staff_payments"),
    path("api/staff/payments/<int:pk>/", api_views.StaffPaymentDetailAPIView.as_view(), name="api_staff_payment_detail"),
    path("api/staff/payments/<int:pk>/verify/", api_views.StaffPaymentVerifyAPIView.as_view(), name="api_staff_payment_verify"),
    path("api/staff/payments/<int:pk>/refund/", api_views.StaffPaymentRefundAPIView.as_view(), name="api_staff_payment_refund"),
    path("api/staff/refunds/", api_views.StaffRefundListAPIView.as_view(), name="api_staff_refunds"),
]

