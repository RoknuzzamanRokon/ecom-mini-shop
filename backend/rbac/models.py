from django.conf import settings
from django.db import models


class Role(models.Model):
    # Defined Staff Roles
    ROLE_SUPER_ADMINISTRATOR = "SUPER_ADMINISTRATOR"
    ROLE_ADMINISTRATOR = "ADMINISTRATOR"
    ROLE_OPERATION_MANAGER = "OPERATION_MANAGER"
    ROLE_SALES_MANAGER = "SALES_MANAGER"
    ROLE_SALES_TEAM = "SALES_TEAM"
    ROLE_FINANCE = "FINANCE"
    ROLE_SUPPORT_TEAM = "SUPPORT_TEAM"
    ROLE_CUSTOMER = "CUSTOMER"

    ROLE_CHOICES = [
        (ROLE_SUPER_ADMINISTRATOR, "Super Administrator"),
        (ROLE_ADMINISTRATOR, "Administrator"),
        (ROLE_OPERATION_MANAGER, "Operation Manager"),
        (ROLE_SALES_MANAGER, "Sales Manager"),
        (ROLE_SALES_TEAM, "Sales Team"),
        (ROLE_FINANCE, "Finance"),
        (ROLE_SUPPORT_TEAM, "Support Team"),
        (ROLE_CUSTOMER, "Customer"),
    ]

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Machine-readable unique role code (e.g. SUPER_ADMINISTRATOR)",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    permissions = models.ManyToManyField(
        "Permission",
        through="RolePermission",
        related_name="roles",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Permission(models.Model):
    code = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Machine-readable permission code in <resource>.<action> format (e.g. products.approve)",
    )
    name = models.CharField(max_length=150)
    resource = models.CharField(max_length=50, db_index=True)
    action = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["resource", "action"]
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"

    def __str__(self):
        return f"{self.code} ({self.name})"

    def save(self, *args, **kwargs):
        if not self.code and self.resource and self.action:
            self.code = f"{self.resource.strip().lower()}.{self.action.strip().lower()}"
        super().save(*args, **kwargs)


class RolePermission(models.Model):
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("role", "permission")
        ordering = ["role", "permission"]
        verbose_name = "Role Permission"
        verbose_name_plural = "Role Permissions"

    def __str__(self):
        return f"{self.role.code} -> {self.permission.code}"


class UserRole(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_roles",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="user_roles",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_user_roles",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("user", "role")
        ordering = ["-assigned_at"]
        verbose_name = "User Role"
        verbose_name_plural = "User Roles"

    def __str__(self):
        return f"{self.user} has role {self.role.code}"
