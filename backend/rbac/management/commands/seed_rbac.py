from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from rbac.models import Permission, Role, RolePermission, UserRole
from rbac.services import assign_user_role

User = get_user_model()

PERMISSIONS_DATA = [
    # Users
    ("users.view", "View Users", "users", "view", "Can view user accounts"),
    ("users.create", "Create Users", "users", "create", "Can create new user accounts"),
    ("users.update", "Update Users", "users", "update", "Can update user details"),
    ("users.delete", "Delete Users", "users", "delete", "Can delete or deactivate user accounts"),
    # Roles & Permissions
    ("roles.view", "View Roles", "roles", "view", "Can view roles and permissions"),
    ("roles.create", "Create Roles", "roles", "create", "Can create new roles"),
    ("roles.update", "Update Roles", "roles", "update", "Can edit roles and their permissions"),
    ("roles.delete", "Delete Roles", "roles", "delete", "Can delete roles"),
    ("roles.assign", "Assign Roles", "roles", "assign", "Can assign roles to users"),
    # Products
    ("products.view", "View Products", "products", "view", "Can view product catalog"),
    ("products.create", "Create Products", "products", "create", "Can create new products"),
    ("products.update", "Update Products", "products", "update", "Can update product details"),
    ("products.delete", "Delete Products", "products", "delete", "Can remove products"),
    ("products.approve", "Approve Products", "products", "approve", "Can approve submitted products"),
    ("products.reject", "Reject Products", "products", "reject", "Can reject submitted products"),
    ("products.publish", "Publish Products", "products", "publish", "Can publish approved products"),
    # Shops
    ("shops.view", "View Shops", "shops", "view", "Can view shop directories"),
    ("shops.create", "Create Shops", "shops", "create", "Can register a new shop"),
    ("shops.update", "Update Shops", "shops", "update", "Can update shop information"),
    ("shops.delete", "Delete Shops", "shops", "delete", "Can delete or close a shop"),
    ("shops.approve", "Approve Shops", "shops", "approve", "Can approve pending shops"),
    # Sellers
    ("sellers.view", "View Sellers", "sellers", "view", "Can view seller profiles"),
    ("sellers.create", "Create Sellers", "sellers", "create", "Can register new sellers"),
    ("sellers.update", "Update Sellers", "sellers", "update", "Can update seller details"),
    ("sellers.approve", "Approve Sellers", "sellers", "approve", "Can verify and approve sellers"),
    ("sellers.suspend", "Suspend Sellers", "sellers", "suspend", "Can suspend seller accounts"),
    # Orders
    ("orders.view", "View Orders", "orders", "view", "Can view orders and fulfillment status"),
    ("orders.create", "Create Orders", "orders", "create", "Can create customer orders"),
    ("orders.update", "Update Orders", "orders", "update", "Can update order progression"),
    ("orders.cancel", "Cancel Orders", "orders", "cancel", "Can cancel customer orders"),
    ("orders.refund", "Refund Orders", "orders", "refund", "Can authorize order refunds"),
    # Payments
    ("payments.view", "View Payments", "payments", "view", "Can inspect transaction ledgers"),
    ("payments.verify", "Verify Payments", "payments", "verify", "Can verify customer payments"),
    ("payments.refund", "Process Refunds", "payments", "refund", "Can process payment refunds"),
    # Points
    ("points.view", "View Points", "points", "view", "Can view point balances and history"),
    ("points.add", "Credit Points", "points", "add", "Can credit points to sellers"),
    ("points.deduct", "Debit Points", "points", "deduct", "Can debit points from sellers"),
    ("points.adjust", "Adjust Points", "points", "adjust", "Can adjust seller point balances"),
    # Reports
    ("reports.view", "View Reports", "reports", "view", "Can access analytical and sales reports"),
    # Customer Profile & Addresses
    ("profile.view", "View Profile", "profile", "view", "Can view customer profile"),
    ("profile.update", "Update Profile", "profile", "update", "Can update customer profile"),
    ("address.view", "View Addresses", "address", "view", "Can view customer addresses"),
    ("address.create", "Create Address", "address", "create", "Can create customer addresses"),
    ("address.update", "Update Address", "address", "update", "Can update customer addresses"),
    ("address.delete", "Delete Address", "address", "delete", "Can delete customer addresses"),
]

ROLES_DATA = [
    (
        Role.ROLE_SUPER_ADMINISTRATOR,
        "Super Administrator",
        "Complete control over all system domains, users, settings, and workflows.",
    ),
    (
        Role.ROLE_ADMINISTRATOR,
        "Administrator",
        "General administration across users, sellers, products, shops, and operations.",
    ),
    (
        Role.ROLE_OPERATION_MANAGER,
        "Operation Manager",
        "Reviews and approves products, shops, and fulfillment workflows.",
    ),
    (
        Role.ROLE_SALES_MANAGER,
        "Sales Manager",
        "Manages sellers, sales team operations, and product marketing.",
    ),
    (
        Role.ROLE_SALES_TEAM,
        "Sales Team",
        "Provides operational assistance to sellers and products.",
    ),
    (
        Role.ROLE_FINANCE,
        "Finance",
        "Oversees payments, transactions, refunds, points adjustments, and financial reports.",
    ),
    (
        Role.ROLE_SUPPORT_TEAM,
        "Support Team",
        "Handles customer inquiries, order issues, complaints, and returns.",
    ),
    (
        Role.ROLE_CUSTOMER,
        "Customer",
        "Standard retail customer account for managing personal profile and delivery addresses.",
    ),
]

ROLE_PERMISSIONS_MAPPING = {
    Role.ROLE_SUPER_ADMINISTRATOR: "__ALL__",
    Role.ROLE_ADMINISTRATOR: [
        "users.view", "users.create", "users.update",
        "roles.view", "roles.assign",
        "products.view", "products.create", "products.update", "products.delete", "products.approve", "products.reject", "products.publish",
        "shops.view", "shops.create", "shops.update", "shops.delete", "shops.approve",
        "sellers.view", "sellers.create", "sellers.update", "sellers.approve", "sellers.suspend",
        "orders.view", "orders.create", "orders.update", "orders.cancel",
        "payments.view",
        "points.view", "points.add", "points.deduct", "points.adjust",
        "reports.view",
        "profile.view", "profile.update",
        "address.view", "address.create", "address.update", "address.delete",
    ],
    Role.ROLE_OPERATION_MANAGER: [
        "products.view", "products.approve", "products.reject", "products.publish",
        "shops.view", "shops.approve",
        "sellers.view",
        "orders.view", "orders.update", "orders.cancel",
        "reports.view",
    ],
    Role.ROLE_SALES_MANAGER: [
        "sellers.view", "sellers.create", "sellers.update", "sellers.approve",
        "products.view", "products.update",
        "orders.view",
        "reports.view",
    ],
    Role.ROLE_SALES_TEAM: [
        "sellers.view",
        "products.view", "products.create", "products.update",
        "orders.view",
    ],
    Role.ROLE_FINANCE: [
        "payments.view", "payments.verify", "payments.refund",
        "orders.view", "orders.refund",
        "points.view", "points.add", "points.deduct", "points.adjust",
        "reports.view",
    ],
    Role.ROLE_SUPPORT_TEAM: [
        "orders.view", "orders.update", "orders.cancel",
        "users.view",
        "sellers.view",
        "shops.view",
        "reports.view",
        "profile.view",
        "address.view",
    ],
    Role.ROLE_CUSTOMER: [
        "profile.view", "profile.update",
        "address.view", "address.create", "address.update", "address.delete",
    ],
}


class Command(BaseCommand):
    help = "Idempotently seed the RBAC permissions, roles, and default role-permission mappings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--assign-superusers",
            action="store_true",
            help="Assign the SUPER_ADMINISTRATOR role to all existing Django superusers",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding RBAC system..."))

        created_perms = 0
        created_roles = 0
        assigned_mappings = 0

        with transaction.atomic():
            # 1. Seed Permissions
            perm_map = {}
            for code, name, resource, action, desc in PERMISSIONS_DATA:
                perm, created = Permission.objects.get_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "resource": resource,
                        "action": action,
                        "description": desc,
                    },
                )
                perm_map[code] = perm
                if created:
                    created_perms += 1

            # 2. Seed Roles
            role_map = {}
            for code, name, desc in ROLES_DATA:
                role, created = Role.objects.get_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "description": desc,
                        "is_active": True,
                    },
                )
                role_map[code] = role
                if created:
                    created_roles += 1

            # 3. Seed Role-Permission Mappings
            all_perms = list(Permission.objects.all())

            for role_code, perms_to_assign in ROLE_PERMISSIONS_MAPPING.items():
                role = role_map[role_code]

                if perms_to_assign == "__ALL__":
                    target_perms = all_perms
                else:
                    target_perms = [perm_map[p] for p in perms_to_assign if p in perm_map]

                for p in target_perms:
                    _, created = RolePermission.objects.get_or_create(
                        role=role,
                        permission=p,
                    )
                    if created:
                        assigned_mappings += 1

            # 4. Optional: Assign SUPER_ADMINISTRATOR to existing superusers
            if options.get("assign_superusers"):
                super_role = role_map[Role.ROLE_SUPER_ADMINISTRATOR]
                superusers = User.objects.filter(is_superuser=True)
                for su in superusers:
                    assign_user_role(su, super_role.code)
                    self.stdout.write(f"  Assigned SUPER_ADMINISTRATOR to user {su.username}")

        self.stdout.write(
            self.style.SUCCESS(
                f"RBAC Seed completed: {created_perms} permissions created (total {Permission.objects.count()}), "
                f"{created_roles} roles created (total {Role.objects.count()}), "
                f"{assigned_mappings} new role-permission links created."
            )
        )
