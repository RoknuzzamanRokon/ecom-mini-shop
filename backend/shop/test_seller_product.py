import threading
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient

from audit.models import AuditLog
from points.models import PointTransaction, ProductCreationCost, SellerWallet
from points.services import InsufficientPointsError, PointService
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.fields import Point
from shops.models import Shop
from .models import Category, Product
from .services import IneligibleSellerError, ProductOwnershipError, ProductService

User = get_user_model()


class BaseSellerProductTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # Create Category
        cls.category = Category.objects.create(
            name="Electronics",
            slug="electronics",
            description="Electronic items",
        )

        # 1. Full Shop Owner (Active) with products.create
        cls.user_full = User.objects.create_user(
            username="seller_full",
            email="seller_full@example.com",
            password="TestPassword123!",
        )
        assign_user_role(cls.user_full, Role.ROLE_SALES_TEAM)  # Contains products.create, products.update, products.view
        cls.seller_full = SellerProfile.objects.create(
            user=cls.user_full,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Apex Electronics",
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop_full = Shop.objects.create(
            owner=cls.seller_full,
            name="Apex Tech Hub",
            slug="apex-tech-hub",
            status=Shop.STATUS_ACTIVE,
            location=Point(90.4125, 23.8103),
        )
        # Give seller initial points (20 pts)
        PointService.credit(
            seller=cls.seller_full,
            amount=20,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Welcome bonus",
        )

        # 2. Limited Shop Owner (Active) with products.create
        cls.user_limited = User.objects.create_user(
            username="seller_limited",
            email="seller_limited@example.com",
            password="TestPassword123!",
        )
        assign_user_role(cls.user_limited, Role.ROLE_SALES_TEAM)
        cls.seller_limited = SellerProfile.objects.create(
            user=cls.user_limited,
            seller_type=SellerProfile.TYPE_LIMITED_SHOP_OWNER,
            business_name="Gadget Kiosk",
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop_limited = Shop.objects.create(
            owner=cls.seller_limited,
            name="Gadget Corner",
            slug="gadget-corner",
            status=Shop.STATUS_ACTIVE,
            location=Point(90.4125, 23.8103),
        )
        PointService.credit(
            seller=cls.seller_limited,
            amount=10,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Welcome bonus",
        )

        # 3. Product Owner (Active) with products.create
        cls.user_prod_owner = User.objects.create_user(
            username="seller_prod_owner",
            email="seller_prod_owner@example.com",
            password="TestPassword123!",
        )
        assign_user_role(cls.user_prod_owner, Role.ROLE_SALES_TEAM)
        cls.seller_prod_owner = SellerProfile.objects.create(
            user=cls.user_prod_owner,
            seller_type=SellerProfile.TYPE_PRODUCT_OWNER,
            business_name="Indie Maker",
            status=SellerProfile.STATUS_ACTIVE,
        )
        PointService.credit(
            seller=cls.seller_prod_owner,
            amount=10,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Welcome bonus",
        )

        # 4. Competitor Seller (Full Shop Owner)
        cls.user_competitor = User.objects.create_user(
            username="seller_competitor",
            email="seller_competitor@example.com",
            password="TestPassword123!",
        )
        assign_user_role(cls.user_competitor, Role.ROLE_SALES_TEAM)
        cls.seller_competitor = SellerProfile.objects.create(
            user=cls.user_competitor,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Rival Electronics",
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop_competitor = Shop.objects.create(
            owner=cls.seller_competitor,
            name="Rival Tech Store",
            slug="rival-tech-store",
            status=Shop.STATUS_ACTIVE,
            location=Point(90.4125, 23.8103),
        )
        PointService.credit(
            seller=cls.seller_competitor,
            amount=15,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Welcome bonus",
        )

        # 5. Suspended Seller
        cls.user_suspended = User.objects.create_user(
            username="seller_suspended",
            email="seller_suspended@example.com",
            password="TestPassword123!",
        )
        assign_user_role(cls.user_suspended, Role.ROLE_SALES_TEAM)
        cls.seller_suspended = SellerProfile.objects.create(
            user=cls.user_suspended,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Suspended Corp",
            status=SellerProfile.STATUS_SUSPENDED,
            suspension_reason="Policy violations",
        )
        cls.shop_suspended = Shop.objects.create(
            owner=cls.seller_suspended,
            name="Suspended Shop",
            slug="suspended-shop",
            status=Shop.STATUS_ACTIVE,
            location=Point(90.4125, 23.8103),
        )
        PointService.credit(
            seller=cls.seller_suspended,
            amount=20,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Initial grant",
        )

        # 6. User WITHOUT products.create permission
        cls.user_unauthorized = User.objects.create_user(
            username="seller_unauth",
            email="seller_unauth@example.com",
            password="TestPassword123!",
        )
        # Assign Support Team (which lacks products.create)
        assign_user_role(cls.user_unauthorized, Role.ROLE_SUPPORT_TEAM)
        cls.seller_unauthorized = SellerProfile.objects.create(
            user=cls.user_unauthorized,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Unauthorized Seller",
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop_unauthorized = Shop.objects.create(
            owner=cls.seller_unauthorized,
            name="Unauthorized Shop",
            slug="unauthorized-shop",
            status=Shop.STATUS_ACTIVE,
            location=Point(90.4125, 23.8103),
        )
        PointService.credit(
            seller=cls.seller_unauthorized,
            amount=20,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Initial grant",
        )


class ProductOwnershipTests(BaseSellerProductTestCase):
    def test_product_belongs_to_shop_and_seller_derived_via_shop(self):
        """Product -> Shop -> Seller hierarchy is strictly enforced without redundant seller fields."""
        product = ProductService.create_product(
            seller=self.seller_full,
            name="Mechanical Keyboard",
            category=self.category,
            shop=self.shop_full,
            description="RGB Tactile Keyboard",
            price=Decimal("120.00"),
            actor=self.user_full,
        )
        self.assertEqual(product.shop, self.shop_full)
        self.assertEqual(product.seller, self.seller_full)
        self.assertEqual(product.owner, self.seller_full)
        self.assertFalse(hasattr(product, "seller_id"))  # No redundant seller_id column

    def test_seller_cannot_create_product_for_another_sellers_shop(self):
        """Seller cannot create a product targeting a shop owned by a competitor."""
        with self.assertRaises(ProductOwnershipError):
            ProductService.create_product(
                seller=self.seller_full,
                name="Illicit Product",
                category=self.category,
                shop=self.shop_competitor,  # Belongs to seller_competitor!
                description="Should fail",
                price=Decimal("50.00"),
                actor=self.user_full,
            )

    def test_seller_cannot_update_another_sellers_product(self):
        """A seller cannot update a product belonging to another seller's shop."""
        comp_product = ProductService.create_product(
            seller=self.seller_competitor,
            name="Competitor Product",
            category=self.category,
            shop=self.shop_competitor,
            description="Original",
            price=Decimal("80.00"),
            actor=self.user_competitor,
        )
        with self.assertRaises(ProductOwnershipError):
            ProductService.update_product(
                product=comp_product,
                seller=self.seller_full,
                data={"name": "Hacked Name"},
                actor=self.user_full,
            )

    def test_seller_cannot_delete_another_sellers_product(self):
        """A seller cannot delete a product belonging to another seller's shop."""
        comp_product = ProductService.create_product(
            seller=self.seller_competitor,
            name="Competitor Product To Delete",
            category=self.category,
            shop=self.shop_competitor,
            description="Original",
            price=Decimal("80.00"),
            actor=self.user_competitor,
        )
        with self.assertRaises(ProductOwnershipError):
            ProductService.delete_product(
                product=comp_product,
                seller=self.seller_full,
                actor=self.user_full,
            )


class ProductPermissionsAndStatusTests(BaseSellerProductTestCase):
    def test_user_without_products_create_permission_rejected(self):
        """A seller lacking 'products.create' RBAC permission is denied."""
        client = APIClient()
        client.force_authenticate(user=self.user_unauthorized)

        payload = {
            "name": "Unauthorized Keyboard",
            "category_id": self.category.id,
            "shop_id": self.shop_unauthorized.id,
            "description": "Will be blocked",
            "price": "99.00",
        }
        res = client.post("/api/products/mine/", payload)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_request_rejected(self):
        """Unauthenticated requests receive 401 Unauthorized."""
        client = APIClient()
        payload = {
            "name": "Anonymous Item",
            "category_id": self.category.id,
            "shop_id": self.shop_full.id,
            "description": "Anon",
            "price": "99.00",
        }
        res = client.post("/api/products/mine/", payload)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_suspended_seller_cannot_create_product(self):
        """A suspended seller cannot create products."""
        client = APIClient()
        client.force_authenticate(user=self.user_suspended)

        payload = {
            "name": "Suspended Product",
            "category_id": self.category.id,
            "shop_id": self.shop_suspended.id,
            "description": "Suspended",
            "price": "99.00",
        }
        res = client.post("/api/products/mine/", payload)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("suspended", str(res.data).lower())

    def test_seller_types_full_and_limited_can_create_products(self):
        """FULL_SHOP_OWNER and LIMITED_SHOP_OWNER can create products for their shops."""
        p_full = ProductService.create_product(
            seller=self.seller_full,
            name="Full Owner Item",
            category=self.category,
            shop=self.shop_full,
            description="Item from full shop owner",
            price=Decimal("45.00"),
            actor=self.user_full,
        )
        self.assertIsNotNone(p_full.id)

        p_limited = ProductService.create_product(
            seller=self.seller_limited,
            name="Limited Owner Item",
            category=self.category,
            shop=self.shop_limited,
            description="Item from limited shop owner",
            price=Decimal("25.00"),
            actor=self.user_limited,
        )
        self.assertIsNotNone(p_limited.id)

    def test_product_owner_seller_cannot_create_product_without_owned_shop(self):
        """PRODUCT_OWNER has no shops; attempting to bind to an unowned shop fails."""
        with self.assertRaises(ProductOwnershipError):
            ProductService.create_product(
                seller=self.seller_prod_owner,
                name="Product Owner Item",
                category=self.category,
                shop=self.shop_full,  # Belongs to seller_full!
                description="Item",
                price=Decimal("15.00"),
                actor=self.user_prod_owner,
            )


class PointCreationCostAndDeductionTests(BaseSellerProductTestCase):
    def test_authoritative_point_cost_configuration(self):
        """Authoritative point cost can be configured dynamically via ProductCreationCost."""
        self.assertEqual(PointService.get_product_creation_cost(), 5)

        # Update cost dynamically
        cost_config, _ = ProductCreationCost.objects.get_or_create(pk=1)
        cost_config.required_points = 8
        cost_config.save()

        self.assertEqual(PointService.get_product_creation_cost(), 8)

        # Restore
        cost_config.required_points = 5
        cost_config.save()

    def test_successful_product_creation_deducts_points_atomically(self):
        """Creating a product deducts 5 points from the seller wallet and records PointTransaction."""
        balance_before = PointService.get_balance(self.seller_full)  # 20
        cost = PointService.get_product_creation_cost()  # 5

        product = ProductService.create_product(
            seller=self.seller_full,
            name="Wireless Mouse",
            category=self.category,
            shop=self.shop_full,
            description="Ergonomic Optical Mouse",
            price=Decimal("35.00"),
            actor=self.user_full,
        )

        balance_after = PointService.get_balance(self.seller_full)
        self.assertEqual(balance_after, balance_before - cost)

        # Verify PointTransaction ledger entry
        txn = PointTransaction.objects.filter(reference_type="PRODUCT", reference_id=str(product.id)).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.transaction_type, PointTransaction.TYPE_PRODUCT_CREATION)
        self.assertEqual(txn.amount, cost)
        self.assertEqual(txn.balance_before, balance_before)
        self.assertEqual(txn.balance_after, balance_after)
        self.assertEqual(txn.seller, self.seller_full)
        self.assertEqual(txn.actor, self.user_full)

    def test_insufficient_points_rejected_without_creating_product_or_txn(self):
        """If seller has insufficient points, product is not created and points are not debited."""
        # Drain wallet so balance is 2 (cost is 5)
        wallet = SellerWallet.objects.get(seller=self.seller_limited)
        wallet.balance = 2
        wallet.save()

        prod_count_before = Product.objects.count()
        txn_count_before = PointTransaction.objects.count()

        with self.assertRaises(InsufficientPointsError):
            ProductService.create_product(
                seller=self.seller_limited,
                name="Budget Earbuds",
                category=self.category,
                shop=self.shop_limited,
                description="Should fail",
                price=Decimal("15.00"),
                actor=self.user_limited,
            )

        # Assert no product created, no transaction, balance unchanged
        self.assertEqual(Product.objects.count(), prod_count_before)
        self.assertEqual(PointTransaction.objects.count(), txn_count_before)
        self.assertEqual(PointService.get_balance(self.seller_limited), 2)


class AuditLoggingTests(BaseSellerProductTestCase):
    def test_audit_log_created_on_product_creation(self):
        """Creating a product creates a unified AuditLog record with actor, shop, seller, and metadata."""
        product = ProductService.create_product(
            seller=self.seller_full,
            name="Gaming Headset",
            category=self.category,
            shop=self.shop_full,
            description="7.1 Surround Sound",
            price=Decimal("95.00"),
            actor=self.user_full,
            ip_address="192.168.1.50",
        )

        log = AuditLog.objects.filter(action="PRODUCT_CREATED", target_type="Product", target_id=str(product.id)).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.user_full)
        self.assertEqual(log.shop, self.shop_full)
        self.assertEqual(log.seller, self.seller_full)
        self.assertEqual(log.ip_address, "192.168.1.50")
        self.assertEqual(log.metadata["points_debited"], 5)
        self.assertEqual(log.metadata["name"], "Gaming Headset")


class AtomicRollbackTests(BaseSellerProductTestCase):
    def test_atomic_rollback_when_audit_fails(self):
        """If audit logging fails after product creation and point debit, everything rolls back."""
        balance_before = PointService.get_balance(self.seller_full)
        prod_count_before = Product.objects.count()
        txn_count_before = PointTransaction.objects.count()

        with patch("audit.services.AuditService.log", side_effect=RuntimeError("Audit system failure")):
            with self.assertRaises(RuntimeError):
                ProductService.create_product(
                    seller=self.seller_full,
                    name="Doomed Monitor",
                    category=self.category,
                    shop=self.shop_full,
                    description="Will rollback",
                    price=Decimal("250.00"),
                    actor=self.user_full,
                )

        # Entire transaction must have rolled back
        self.assertEqual(Product.objects.filter(name="Doomed Monitor").count(), 0)
        self.assertEqual(Product.objects.count(), prod_count_before)
        self.assertEqual(PointTransaction.objects.count(), txn_count_before)
        self.assertEqual(PointService.get_balance(self.seller_full), balance_before)


class SellerProductAPITests(BaseSellerProductTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_api_seller_product_creation_flow(self):
        """POST /api/products/mine/ creates product, debits points, and returns 201."""
        self.client.force_authenticate(user=self.user_full)
        balance_before = PointService.get_balance(self.seller_full)

        payload = {
            "name": "Smart Watch Series 7",
            "category_id": self.category.id,
            "shop_id": self.shop_full.id,
            "description": "Fitness tracking smartwatch",
            "price": "199.99",
            "old_price": "249.99",
            "stock": 15,
            "badge": "HOT",
        }
        res = self.client.post("/api/products/mine/", payload)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["name"], "Smart Watch Series 7")
        self.assertEqual(res.data["status"], Product.STATUS_DRAFT)
        self.assertEqual(res.data["shop"]["id"], self.shop_full.id)
        self.assertEqual(res.data["owner_business_name"], self.seller_full.business_name)

        # Balance debited
        balance_after = PointService.get_balance(self.seller_full)
        self.assertEqual(balance_after, balance_before - 5)

    def test_api_seller_cross_seller_shop_assignment_rejected(self):
        """POST /api/products/mine/ rejecting when seller tries to assign competitor shop."""
        self.client.force_authenticate(user=self.user_full)
        payload = {
            "name": "Tampered Product",
            "category_id": self.category.id,
            "shop_id": self.shop_competitor.id,  # Competitor shop
            "description": "Should fail",
            "price": "99.99",
        }
        res = self.client.post("/api/products/mine/", payload)
        self.assertIn(res.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN))
        self.assertIn("own", str(res.data).lower())

    def test_api_seller_product_creation_without_shop_id_auto_resolves_assigned_shop(self):
        """POST /api/products/mine/ omitting shop_id auto-resolves the seller's single assigned Shop."""
        self.client.force_authenticate(user=self.user_full)
        balance_before = PointService.get_balance(self.seller_full)

        payload = {
            "name": "Auto-Resolved Shop Product",
            "category_id": self.category.id,
            "description": "No shop_id supplied by the client",
            "price": "49.99",
        }
        res = self.client.post("/api/products/mine/", payload)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["shop"]["id"], self.shop_full.id)

        balance_after = PointService.get_balance(self.seller_full)
        self.assertEqual(balance_after, balance_before - 5)

    def test_api_seller_without_assigned_shop_cannot_create_product(self):
        """A Shop Owner with no assigned Shop yet gets a clear error, not a crash, when omitting shop_id."""
        self.client.force_authenticate(user=self.user_prod_owner)
        payload = {
            "name": "No Shop Product",
            "category_id": self.category.id,
            "description": "Product Owner has no assigned Shop",
            "price": "20.00",
        }
        res = self.client.post("/api/products/mine/", payload)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("shop", str(res.data).lower())

    def test_api_seller_with_inconsistent_multiple_shops_gets_safe_error_not_silent_pick(self):
        """
        Single-shop-per-seller is a hard business rule, but nothing at the DB layer
        prevents legacy/inconsistent data from giving one seller two Shops. When
        that happens, omitting shop_id must NOT silently pick one of them (that
        would risk products landing under the wrong Shop) - it must fail safely.
        """
        Shop.objects.create(
            owner=self.seller_full,
            name="Second Legacy Shop",
            slug="second-legacy-shop",
            status=Shop.STATUS_ACTIVE,
            location=Point(90.4125, 23.8103),
        )

        self.client.force_authenticate(user=self.user_full)
        prod_count_before = Product.objects.count()
        balance_before = PointService.get_balance(self.seller_full)

        payload = {
            "name": "Ambiguous Shop Product",
            "category_id": self.category.id,
            "description": "No shop_id supplied while seller owns 2 shops",
            "price": "20.00",
        }
        res = self.client.post("/api/products/mine/", payload)
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("multiple", str(res.data).lower())

        # Nothing was created and no points were touched.
        self.assertEqual(Product.objects.count(), prod_count_before)
        self.assertEqual(PointService.get_balance(self.seller_full), balance_before)

    def test_api_seller_cannot_change_product_shop_to_another_sellers_shop(self):
        """PATCH /api/products/mine/<id>/ rejects reassigning a product to another seller's Shop."""
        product = ProductService.create_product(
            seller=self.seller_full,
            name="Stable Ownership Item",
            category=self.category,
            shop=self.shop_full,
            description="Should remain on shop_full",
            price=Decimal("40.00"),
            actor=self.user_full,
        )

        self.client.force_authenticate(user=self.user_full)
        res = self.client.patch(
            f"/api/products/mine/{product.id}/",
            {"shop_id": self.shop_competitor.id},
        )
        self.assertIn(res.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN))
        product.refresh_from_db()
        self.assertEqual(product.shop, self.shop_full)

    def test_api_seller_product_list_only_shows_own_products(self):
        """GET /api/products/mine/ lists only products belonging to the authenticated seller's shops."""
        # Create product for full seller
        p_full = ProductService.create_product(
            seller=self.seller_full,
            name="Seller Full Product",
            category=self.category,
            shop=self.shop_full,
            description="Item",
            price=Decimal("10.00"),
            actor=self.user_full,
        )
        # Create product for competitor
        p_comp = ProductService.create_product(
            seller=self.seller_competitor,
            name="Competitor Product",
            category=self.category,
            shop=self.shop_competitor,
            description="Item",
            price=Decimal("20.00"),
            actor=self.user_competitor,
        )

        self.client.force_authenticate(user=self.user_full)
        res = self.client.get("/api/products/mine/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        results = res.data["results"] if "results" in res.data else res.data
        result_ids = [item["id"] for item in results]
        self.assertIn(p_full.id, result_ids)
        self.assertNotIn(p_comp.id, result_ids)

    def test_api_seller_product_update_and_delete(self):
        """PATCH /api/products/mine/<id>/ updates product; DELETE removes product."""
        p = ProductService.create_product(
            seller=self.seller_full,
            name="Initial Name",
            category=self.category,
            shop=self.shop_full,
            description="Initial desc",
            price=Decimal("50.00"),
            actor=self.user_full,
        )

        self.client.force_authenticate(user=self.user_full)

        # Update
        patch_res = self.client.patch(f"/api/products/mine/{p.id}/", {"name": "Updated Name", "price": "55.00"})
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["name"], "Updated Name")
        self.assertEqual(Decimal(str(patch_res.data["price"])), Decimal("55.00"))

        # Delete without products.delete permission -> 403
        del_unauth_res = self.client.delete(f"/api/products/mine/{p.id}/")
        self.assertEqual(del_unauth_res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Product.objects.filter(id=p.id).exists())

        # Grant products.delete permission via Administrator role
        assign_user_role(self.user_full, Role.ROLE_ADMINISTRATOR)
        del_res = self.client.delete(f"/api/products/mine/{p.id}/")
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Product.objects.filter(id=p.id).exists())



class ConcurrencySafetyTests(TransactionTestCase):
    """
    Tests concurrency safety against race conditions and wallet overdraws
    using MySQL transactional row locks.
    """
    def setUp(self):
        call_command("seed_rbac")
        self.category = Category.objects.create(name="Gizmos", slug="gizmos")
        self.user = User.objects.create_user(username="concur_seller", email="concur@test.com", password="Pass123!")
        assign_user_role(self.user, Role.ROLE_SALES_TEAM)
        self.seller = SellerProfile.objects.create(
            user=self.user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Fast Tech",
            status=SellerProfile.STATUS_ACTIVE,
        )
        self.shop = Shop.objects.create(
            owner=self.seller,
            name="Fast Tech Shop",
            slug="fast-tech-shop",
            status=Shop.STATUS_ACTIVE,
            location=Point(90.4125, 23.8103),
        )
        # Give wallet exactly 5 points (enough for only 1 product)
        PointService.credit(
            seller=self.seller,
            amount=5,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Exact 1 product points",
        )

    def test_concurrent_product_creation_prevents_negative_balance(self):
        """
        When two concurrent creation requests occur simultaneously with balance for only 1,
        exactly one succeeds and one fails with InsufficientPointsError.
        """
        results = []
        errors = []

        def worker(idx):
            try:
                p = ProductService.create_product(
                    seller=self.seller,
                    name=f"Concurrent Product {idx}",
                    category=self.category,
                    shop=self.shop,
                    description="Stress test item",
                    price=Decimal("20.00"),
                    actor=self.user,
                )
                results.append(p)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker, args=(1,))
        t2 = threading.Thread(target=worker, args=(2,))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly 1 product created
        self.assertEqual(len(results), 1)
        # Exactly 1 failure
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], InsufficientPointsError)

        # Wallet balance ends exactly at 0, never negative
        final_balance = PointService.get_balance(self.seller)
        self.assertEqual(final_balance, 0)
