from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from customers.models import Address, CustomerProfile
from customers.services import AddressService, CustomerService
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile

User = get_user_model()


class CustomerProfileAndAddressTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # Create user with ROLE_CUSTOMER
        cls.customer_user = User.objects.create_user(
            username="customer_user",
            email="customer@example.com",
            password="Password123!",
            first_name="Rahim",
            last_name="Uddin",
        )
        assign_user_role(cls.customer_user, Role.ROLE_CUSTOMER)

        # Create user without any roles (no permissions)
        cls.plain_user = User.objects.create_user(
            username="plain_user",
            email="plain@example.com",
            password="Password123!",
            first_name="No",
            last_name="Roles",
        )

        # Create another customer user (User B) for isolation tests
        cls.other_customer = User.objects.create_user(
            username="other_customer",
            email="other@example.com",
            password="Password123!",
            first_name="Karim",
            last_name="Khan",
        )
        assign_user_role(cls.other_customer, Role.ROLE_CUSTOMER)

        # Create a superuser
        cls.admin_user = User.objects.create_superuser(
            username="admin_user",
            email="admin@example.com",
            password="AdminPassword123!",
        )

    def test_get_customer_profile_auto_initialization(self):
        """Authenticated user with profile.view can retrieve and auto-initialize customer profile."""
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.get("/api/profile/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "customer_user")
        self.assertEqual(response.data["email"], "customer@example.com")
        self.assertEqual(response.data["first_name"], "Rahim")
        self.assertEqual(response.data["last_name"], "Uddin")
        self.assertEqual(response.data["display_name"], "Rahim Uddin")

        # Confirm database profile exists
        profile = CustomerProfile.objects.filter(user=self.customer_user).first()
        self.assertIsNotNone(profile)

    def test_get_customer_profile_unauthenticated(self):
        """Unauthenticated request is rejected with 401."""
        response = self.client.get("/api/profile/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_customer_profile_without_permission(self):
        """User without profile.view permission is rejected with 403."""
        self.client.force_authenticate(user=self.plain_user)
        response = self.client.get("/api/profile/me/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_customer_profile_and_audit_log(self):
        """Authenticated user with profile.update can patch profile, generating an AuditLog."""
        self.client.force_authenticate(user=self.customer_user)
        payload = {
            "display_name": "Rahim The Shopper",
            "phone": "+8801712345678",
            "gender": "MALE",
        }
        response = self.client.patch("/api/profile/me/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["display_name"], "Rahim The Shopper")
        self.assertEqual(response.data["phone"], "+8801712345678")
        self.assertEqual(response.data["gender"], "MALE")

        # Verify audit log was created
        audit_entry = AuditLog.objects.filter(
            actor=self.customer_user,
            action="PROFILE_UPDATED",
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertIn("display_name", audit_entry.metadata["changed_fields"])

    def test_update_customer_profile_without_permission(self):
        """User without profile.update permission cannot update profile."""
        self.client.force_authenticate(user=self.plain_user)
        payload = {"display_name": "Should Fail"}
        response = self.client.patch("/api/profile/me/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # --- Address Model & Default Switching Tests ---

    def test_first_address_auto_default(self):
        """The first address created for a user automatically becomes default."""
        address = AddressService.create_address(
            user=self.customer_user,
            data={
                "label": "Home",
                "recipient_name": "Rahim Uddin",
                "phone": "+8801711111111",
                "address_line_1": "House 10, Road 5",
                "area": "Dhanmondi",
                "city": "Dhaka",
                "postal_code": "1205",
                "country": "Bangladesh",
                "is_default": False,  # Should be forced to True because it's first
            },
        )
        self.assertTrue(address.is_default)
        self.assertEqual(address.default_flag, 1)

    def test_second_address_not_default_leaves_first_intact(self):
        """Adding a non-default second address does not change the first default address."""
        addr1 = AddressService.create_address(
            user=self.customer_user,
            data={
                "label": "Home",
                "recipient_name": "Rahim",
                "phone": "+8801711111111",
                "address_line_1": "House 1",
                "city": "Dhaka",
                "postal_code": "1205",
            },
        )
        addr2 = AddressService.create_address(
            user=self.customer_user,
            data={
                "label": "Work",
                "recipient_name": "Rahim Office",
                "phone": "+8801722222222",
                "address_line_1": "Level 4, Gulshan Tower",
                "city": "Dhaka",
                "postal_code": "1212",
                "is_default": False,
            },
        )
        addr1.refresh_from_db()
        addr2.refresh_from_db()
        self.assertTrue(addr1.is_default)
        self.assertEqual(addr1.default_flag, 1)
        self.assertFalse(addr2.is_default)
        self.assertIsNone(addr2.default_flag)

    def test_second_address_as_default_demotes_first(self):
        """Adding a second address with is_default=True atomically demotes the previous default."""
        addr1 = AddressService.create_address(
            user=self.customer_user,
            data={
                "label": "Home",
                "recipient_name": "Rahim",
                "phone": "+8801711111111",
                "address_line_1": "House 1",
                "city": "Dhaka",
                "postal_code": "1205",
            },
        )
        self.assertTrue(addr1.is_default)

        addr2 = AddressService.create_address(
            user=self.customer_user,
            data={
                "label": "Work",
                "recipient_name": "Rahim Office",
                "phone": "+8801722222222",
                "address_line_1": "Tower 2",
                "city": "Dhaka",
                "postal_code": "1212",
                "is_default": True,
            },
        )
        addr1.refresh_from_db()
        addr2.refresh_from_db()

        self.assertFalse(addr1.is_default)
        self.assertIsNone(addr1.default_flag)
        self.assertTrue(addr2.is_default)
        self.assertEqual(addr2.default_flag, 1)

    def test_database_engine_unique_default_constraint(self):
        """Direct DB insertion of multiple default_flag=1 for same user violates MySQL UniqueConstraint."""
        Address.objects.create(
            user=self.customer_user,
            label="Addr 1",
            recipient_name="Rahim",
            phone="123",
            address_line_1="Line 1",
            city="Dhaka",
            postal_code="1000",
            is_default=True,
            default_flag=1,
        )
        with self.assertRaises(IntegrityError):
            Address.objects.create(
                user=self.customer_user,
                label="Addr 2",
                recipient_name="Rahim",
                phone="456",
                address_line_1="Line 2",
                city="Dhaka",
                postal_code="1000",
                is_default=True,
                default_flag=1,
            )

    def test_delete_default_address_promotes_remaining(self):
        """Deleting the default address promotes the next remaining address to default."""
        addr1 = AddressService.create_address(
            user=self.customer_user,
            data={
                "label": "Home",
                "recipient_name": "Rahim",
                "phone": "111",
                "address_line_1": "Line 1",
                "city": "Dhaka",
                "postal_code": "1000",
            },
        )
        addr2 = AddressService.create_address(
            user=self.customer_user,
            data={
                "label": "Work",
                "recipient_name": "Rahim",
                "phone": "222",
                "address_line_1": "Line 2",
                "city": "Dhaka",
                "postal_code": "1000",
                "is_default": False,
            },
        )
        self.assertTrue(addr1.is_default)
        self.assertFalse(addr2.is_default)

        # Delete addr1 (which was default)
        AddressService.delete_address(addr1)

        addr2.refresh_from_db()
        self.assertTrue(addr2.is_default)
        self.assertEqual(addr2.default_flag, 1)

    def test_delete_only_address_leaves_zero_defaults(self):
        """Deleting the user's only address leaves zero addresses safely."""
        addr = AddressService.create_address(
            user=self.customer_user,
            data={
                "label": "Home",
                "recipient_name": "Rahim",
                "phone": "111",
                "address_line_1": "Line 1",
                "city": "Dhaka",
                "postal_code": "1000",
            },
        )
        AddressService.delete_address(addr)
        self.assertEqual(Address.objects.filter(user=self.customer_user).count(), 0)

    # --- API Endpoints & Ownership Isolation Tests ---

    def test_address_crud_and_ownership_isolation(self):
        """Full CRUD on addresses via API, verifying strict user isolation."""
        self.client.force_authenticate(user=self.customer_user)

        # 1. Create Address
        create_payload = {
            "label": "Office",
            "recipient_name": "Rahim Tech",
            "phone": "+8801811111111",
            "address_line_1": "123 Banani Road 11",
            "area": "Banani",
            "city": "Dhaka",
            "postal_code": "1213",
            "country": "Bangladesh",
            "latitude": "23.793700",
            "longitude": "90.404800",
        }
        res_create = self.client.post("/api/addresses/", create_payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        address_id = res_create.data["id"]
        self.assertTrue(res_create.data["is_default"])  # Auto-default on first

        # 2. List Addresses
        res_list = self.client.get("/api/addresses/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data), 1)

        # 3. Retrieve Detail
        res_get = self.client.get(f"/api/addresses/{address_id}/")
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertEqual(res_get.data["recipient_name"], "Rahim Tech")

        # 4. User B attempts to access User A's address -> DENIED (403 or 404)
        self.client.force_authenticate(user=self.other_customer)
        res_unauthorized_get = self.client.get(f"/api/addresses/{address_id}/")
        self.assertIn(res_unauthorized_get.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        res_unauthorized_patch = self.client.patch(
            f"/api/addresses/{address_id}/",
            {"recipient_name": "Hacked"},
            format="json",
        )
        self.assertIn(res_unauthorized_patch.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        res_unauthorized_del = self.client.delete(f"/api/addresses/{address_id}/")
        self.assertIn(res_unauthorized_del.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        # 5. User A updates address
        self.client.force_authenticate(user=self.customer_user)
        res_patch = self.client.patch(
            f"/api/addresses/{address_id}/",
            {"recipient_name": "Rahim Uddin Updated"},
            format="json",
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data["recipient_name"], "Rahim Uddin Updated")

        # 6. User A deletes address
        res_del = self.client.delete(f"/api/addresses/{address_id}/")
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)

    def test_address_set_default_endpoint(self):
        """Promoting an address via /api/addresses/<id>/set-default/."""
        self.client.force_authenticate(user=self.customer_user)

        # Create two addresses
        addr1 = AddressService.create_address(
            user=self.customer_user,
            data={
                "label": "Home",
                "recipient_name": "Rahim",
                "phone": "111",
                "address_line_1": "Line 1",
                "city": "Dhaka",
                "postal_code": "1000",
            },
        )
        addr2 = AddressService.create_address(
            user=self.customer_user,
            data={
                "label": "Work",
                "recipient_name": "Rahim",
                "phone": "222",
                "address_line_1": "Line 2",
                "city": "Dhaka",
                "postal_code": "1000",
                "is_default": False,
            },
        )
        self.assertTrue(addr1.is_default)
        self.assertFalse(addr2.is_default)

        # Set addr2 as default via endpoint
        res = self.client.post(f"/api/addresses/{addr2.id}/set-default/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_default"])

        addr1.refresh_from_db()
        addr2.refresh_from_db()
        self.assertFalse(addr1.is_default)
        self.assertTrue(addr2.is_default)

    def test_create_address_without_permission(self):
        """User without address.create permission is rejected with 403."""
        self.client.force_authenticate(user=self.plain_user)
        payload = {
            "label": "Home",
            "recipient_name": "Test",
            "phone": "123",
            "address_line_1": "Street",
            "city": "Dhaka",
            "postal_code": "1000",
        }
        res = self.client.post("/api/addresses/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # --- Coordinate Validation Tests ---

    def test_coordinate_validation_rules(self):
        """Validates that latitude and longitude must be paired and in range."""
        self.client.force_authenticate(user=self.customer_user)

        # Missing longitude
        payload_missing_lng = {
            "recipient_name": "Rahim",
            "phone": "123",
            "address_line_1": "Street",
            "city": "Dhaka",
            "postal_code": "1000",
            "latitude": "23.8103",
        }
        res = self.client.post("/api/addresses/", payload_missing_lng, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Latitude out of range (> 90)
        payload_invalid_lat = {
            "recipient_name": "Rahim",
            "phone": "123",
            "address_line_1": "Street",
            "city": "Dhaka",
            "postal_code": "1000",
            "latitude": "95.0000",
            "longitude": "90.0000",
        }
        res = self.client.post("/api/addresses/", payload_invalid_lat, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Longitude out of range (> 180)
        payload_invalid_lng = {
            "recipient_name": "Rahim",
            "phone": "123",
            "address_line_1": "Street",
            "city": "Dhaka",
            "postal_code": "1000",
            "latitude": "23.0000",
            "longitude": "195.0000",
        }
        res = self.client.post("/api/addresses/", payload_invalid_lng, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Coexistence Tests ---

    def test_user_can_coexist_as_seller_and_customer(self):
        """A user can hold both a SellerProfile and a CustomerProfile simultaneously."""
        # Create seller profile for customer_user
        seller = SellerProfile.objects.create(
            user=self.customer_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Rahim Mega Store",
        )
        # Create customer profile for customer_user
        customer = CustomerService.get_or_create_profile(self.customer_user)

        self.assertEqual(self.customer_user.seller_profile, seller)
        self.assertEqual(self.customer_user.customer_profile, customer)
        self.assertEqual(customer.user, seller.user)
