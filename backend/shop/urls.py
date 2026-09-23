from django.urls import path

from . import api_views, views

app_name = "shop"

urlpatterns = [
    # Traditional Django template views
    path("", views.product_list, name="product_list"),
    path("category/<slug:category_slug>/", views.product_list, name="category"),
    path("product/<slug:slug>/", views.product_detail, name="product_detail"),

    # REST API endpoints for Next.js frontend
    path("api/categories/", api_views.CategoryListView.as_view(), name="api_categories"),
    path("api/products/mine/", api_views.SellerProductListCreateAPIView.as_view(), name="api_seller_products"),
    path("api/products/mine/<int:pk>/", api_views.SellerProductDetailAPIView.as_view(), name="api_seller_product_detail"),
    path("api/products/", api_views.ProductListAPIView.as_view(), name="api_products"),
    path("api/products/<int:product_id>/reviews/", api_views.ProductReviewListAPIView.as_view(), name="api_product_reviews"),
    path("api/products/<int:pk>/", api_views.ProductDetailAPIView.as_view(), name="api_product_detail_pk"),
    path("api/products/<slug:slug>/", api_views.ProductDetailAPIView.as_view(), name="api_product_detail"),
    path("api/hot-deals/", api_views.HotDealAPIView.as_view(), name="api_hot_deal"),
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
    # Staff Order Operations APIs (Task 16)
    path("api/staff/orders/", api_views.StaffOrderListAPIView.as_view(), name="api_staff_orders"),
    path("api/staff/orders/<int:pk>/", api_views.StaffOrderDetailAPIView.as_view(), name="api_staff_order_detail_pk"),
    path("api/staff/orders/<str:order_number>/", api_views.StaffOrderDetailAPIView.as_view(), name="api_staff_order_detail"),
    path("api/staff/orders/<int:pk>/status/", api_views.StaffOrderStatusAPIView.as_view(), name="api_staff_order_status_pk"),
    path("api/staff/orders/<str:order_number>/status/", api_views.StaffOrderStatusAPIView.as_view(), name="api_staff_order_status"),

    # Admin & Platform Governance APIs (Task 17)
    path("api/admin/users/", api_views.AdminUserListAPIView.as_view(), name="admin_users_list"),
    path("api/admin/users/<int:pk>/", api_views.AdminUserDetailAPIView.as_view(), name="admin_users_detail"),
    path("api/admin/roles/", api_views.AdminRoleListCreateAPIView.as_view(), name="admin_roles_list_create"),
    path("api/admin/roles/<int:pk>/", api_views.AdminRoleDetailAPIView.as_view(), name="admin_roles_detail"),
    path("api/admin/permissions/", api_views.AdminPermissionCatalogAPIView.as_view(), name="admin_permissions_catalog"),
    path("api/admin/sellers/", api_views.AdminSellerListAPIView.as_view(), name="admin_sellers_list"),
    path("api/admin/sellers/<int:pk>/", api_views.AdminSellerDetailAPIView.as_view(), name="admin_sellers_detail"),
    path("api/admin/sellers/<int:pk>/status/", api_views.AdminSellerStatusAPIView.as_view(), name="admin_sellers_status"),
    path("api/admin/shops/", api_views.AdminShopListAPIView.as_view(), name="admin_shops_list"),
    path("api/admin/shops/<int:pk>/", api_views.AdminShopDetailAPIView.as_view(), name="admin_shops_detail"),
    path("api/admin/shops/<int:pk>/status/", api_views.AdminShopStatusAPIView.as_view(), name="admin_shops_status"),
    path("api/admin/products/", api_views.AdminProductListAPIView.as_view(), name="admin_products_list"),
    path("api/admin/products/<int:pk>/", api_views.AdminProductDetailAPIView.as_view(), name="admin_products_detail"),
    path("api/admin/products/<int:pk>/status/", api_views.AdminProductStatusAPIView.as_view(), name="admin_products_status"),
    path("api/admin/categories/", api_views.AdminCategoryListCreateAPIView.as_view(), name="admin_categories_list_create"),
    path("api/admin/categories/<int:pk>/", api_views.AdminCategoryDetailAPIView.as_view(), name="admin_categories_detail"),
    path("api/admin/customers/", api_views.AdminCustomerListAPIView.as_view(), name="admin_customers_list"),
    path("api/admin/customers/<int:pk>/", api_views.AdminCustomerDetailAPIView.as_view(), name="admin_customers_detail"),
    path("api/admin/metrics/", api_views.AdminMetricsAPIView.as_view(), name="admin_metrics"),
    path("api/admin/audit-logs/", api_views.AdminAuditLogListAPIView.as_view(), name="admin_audit_logs_list"),
]

