import math
from typing import Any, Optional, Tuple

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.expressions import RawSQL
from django.utils import timezone

from sellers.models import SellerProfile
from shops.fields import Point
from .models import Shop


class ShopError(Exception):
    """Base exception for shop domain errors."""
    pass


class InvalidShopTransitionError(ShopError):
    """Raised when an illegal lifecycle state transition is requested."""
    pass


class IneligibleSellerError(ShopError):
    """Raised when an ineligible seller attempts shop operations."""
    pass


class ShopLimitExceededError(ShopError):
    """Raised when a seller attempts to exceed their allowed shop quota."""
    pass


def validate_coordinates(latitude: Any, longitude: Any) -> Tuple[float, float]:
    """
    Centralized validator for geographic coordinates.
    - latitude: [-90.0, 90.0]
    - longitude: [-180.0, 180.0]
    Rejects missing, null, NaN, Inf, non-numeric, or out-of-bounds coordinates.
    Returns (float(latitude), float(longitude)).
    """
    if latitude is None or longitude is None:
        raise ValidationError("Both 'latitude' and 'longitude' coordinates are required.")

    try:
        lat = float(latitude)
        lng = float(longitude)
    except (ValueError, TypeError):
        raise ValidationError("Coordinates must be valid numeric values.")

    if math.isnan(lat) or math.isinf(lat) or math.isnan(lng) or math.isinf(lng):
        raise ValidationError("Coordinates cannot be NaN or Infinite.")

    if lat < -90.0 or lat > 90.0:
        raise ValidationError(f"Latitude must be between -90.0 and 90.0 degrees. Received: {lat}.")

    if lng < -180.0 or lng > 180.0:
        raise ValidationError(f"Longitude must be between -180.0 and 180.0 degrees. Received: {lng}.")

    return round(lat, 7), round(lng, 7)


def validate_radius(radius_km: Any, max_radius_km: float = 1000.0) -> float:
    """
    Centralized validator for search radius in kilometers.
    - radius > 0
    - radius <= max_radius_km (default 1000 km)
    """
    if radius_km is None:
        raise ValidationError("Search 'radius' in kilometers is required.")

    try:
        rad = float(radius_km)
    except (ValueError, TypeError):
        raise ValidationError("Search 'radius' must be a valid numeric value.")

    if math.isnan(rad) or math.isinf(rad):
        raise ValidationError("Search 'radius' cannot be NaN or Infinite.")

    if rad <= 0.0:
        raise ValidationError(f"Search 'radius' must be greater than 0 km. Received: {rad}.")

    if rad > max_radius_km:
        raise ValidationError(f"Search 'radius' cannot exceed {max_radius_km} km. Received: {rad}.")

    return round(rad, 4)


class ShopService:
    """
    Centralized domain service managing Shop lifecycle, ownership,
    seller type restrictions, and administrative transitions.
    """

    @classmethod
    def validate_seller_eligibility_for_creation(cls, seller: SellerProfile):
        """Verifies seller operational status and seller-type capabilities for shop creation."""
        if not seller.is_operational:
            raise IneligibleSellerError(
                f"Seller must be approved and active to create a shop. Current status: '{seller.status}'."
            )

        if seller.seller_type == SellerProfile.TYPE_PRODUCT_OWNER:
            raise IneligibleSellerError(
                "Product Owners are not permitted to create shops under system business rules."
            )

        # Limited Shop Owners are restricted to a single shop
        if seller.seller_type == SellerProfile.TYPE_LIMITED_SHOP_OWNER and seller.shops.count() >= 1:
            raise ShopLimitExceededError(
                "Limited Shop Owners are restricted to a maximum of 1 shop."
            )

    @classmethod
    @transaction.atomic
    def create_shop(
        cls,
        seller: SellerProfile,
        name: str,
        description: str = "",
        phone: str = "",
        address: str = "",
        location: Any = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        logo=None,
        cover_image=None,
        submit_for_review: bool = False,
    ) -> Shop:
        """Creates a new Shop for an eligible seller, optionally submitting directly for staff review."""
        cls.validate_seller_eligibility_for_creation(seller)

        initial_status = Shop.STATUS_PENDING if submit_for_review else Shop.STATUS_DRAFT

        shop = Shop(
            owner=seller,
            name=name.strip(),
            description=description.strip(),
            phone=phone.strip(),
            address=address.strip(),
            status=initial_status,
        )

        if latitude is not None and longitude is not None:
            lat, lng = validate_coordinates(latitude, longitude)
            shop.location = Point(longitude=lng, latitude=lat)
        elif location:
            shop.location = location

        if logo:
            shop.logo = logo
        if cover_image:
            shop.cover_image = cover_image

        shop.save()
        return shop

    @classmethod
    @transaction.atomic
    def update_shop(cls, shop: Shop, seller: SellerProfile, **fields) -> Shop:
        """Updates shop profile fields while enforcing ownership and operational seller status."""
        if shop.owner != seller:
            raise PermissionDenied("You do not have permission to modify this shop.")

        if not seller.is_operational:
            raise IneligibleSellerError("Suspended or inactive sellers cannot modify shop details.")

        if "latitude" in fields and "longitude" in fields:
            lat, lng = validate_coordinates(fields.pop("latitude"), fields.pop("longitude"))
            shop.location = Point(longitude=lng, latitude=lat)

        allowed_fields = {
            "name",
            "description",
            "phone",
            "address",
            "location",
            "logo",
            "cover_image",
        }

        for key, value in fields.items():
            if key in allowed_fields:
                setattr(shop, key, value)

        shop.save()
        return shop

    @classmethod
    @transaction.atomic
    def update_shop_location(
        cls,
        shop: Shop,
        seller: SellerProfile,
        latitude: Any,
        longitude: Any,
    ) -> Shop:
        """
        Updates the spatial geographic location of a shop.
        Enforces seller ownership and operational seller status.
        """
        if shop.owner != seller:
            raise PermissionDenied("You do not have permission to modify this shop.")

        if not seller.is_operational:
            raise IneligibleSellerError("Suspended or inactive sellers cannot modify shop details.")

        lat, lng = validate_coordinates(latitude, longitude)
        shop.location = Point(longitude=lng, latitude=lat)
        shop.save()
        return shop

    @classmethod
    def get_nearby_shops(
        cls,
        latitude: Any,
        longitude: Any,
        radius_km: Any,
        max_radius_km: float = 1000.0,
    ):
        """
        Executes a MySQL 8 native spatial query using ST_Distance_Sphere.
        Returns public APPROVED/ACTIVE shops within radius_km, ordered nearest-first.
        Excludes DRAFT, PENDING, SUSPENDED, and REJECTED shops.
        """
        lat, lng = validate_coordinates(latitude, longitude)
        rad = validate_radius(radius_km, max_radius_km=max_radius_km)

        origin_wkt = f"POINT({lng:.7f} {lat:.7f})"
        radius_meters = rad * 1000.0

        distance_meters_sql = RawSQL(
            "ST_Distance_Sphere(location, ST_GeomFromText(%s, 4326, 'axis-order=long-lat'))",
            (origin_wkt,),
        )
        distance_km_sql = RawSQL(
            "ROUND(ST_Distance_Sphere(location, ST_GeomFromText(%s, 4326, 'axis-order=long-lat')) / 1000.0, 3)",
            (origin_wkt,),
        )

        qs = (
            Shop.objects.filter(
                status__in=[Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE]
            )
            .annotate(
                distance_meters=distance_meters_sql,
                distance_km=distance_km_sql,
            )
            .filter(
                distance_meters__lte=radius_meters
            )
            .order_by("distance_meters")
        )
        return qs

    @classmethod
    @transaction.atomic
    def submit_for_review(cls, shop: Shop, seller: SellerProfile) -> Shop:
        """Submits a DRAFT or REJECTED shop for staff review."""
        if shop.owner != seller:
            raise PermissionDenied("You do not have permission to submit this shop.")

        if not seller.is_operational:
            raise IneligibleSellerError("Suspended or inactive sellers cannot submit shops for review.")

        if shop.status not in (Shop.STATUS_DRAFT, Shop.STATUS_REJECTED):
            raise InvalidShopTransitionError(
                f"Cannot submit shop with status '{shop.status}'. Only DRAFT or REJECTED shops can be submitted."
            )

        shop.status = Shop.STATUS_PENDING
        shop.save()
        return shop

    @classmethod
    @transaction.atomic
    def approve_shop(cls, shop: Shop, staff_user) -> Shop:
        """Approves and activates a pending shop."""
        if shop.status not in (Shop.STATUS_PENDING, Shop.STATUS_DRAFT):
            raise InvalidShopTransitionError(
                f"Cannot approve shop with status '{shop.status}'. Only PENDING or DRAFT shops can be approved."
            )

        shop.status = Shop.STATUS_ACTIVE
        shop.reviewed_by = staff_user
        shop.reviewed_at = timezone.now()
        shop.approved_at = timezone.now()
        shop.rejection_reason = ""
        shop.save()
        return shop

    @classmethod
    @transaction.atomic
    def reject_shop(cls, shop: Shop, staff_user, reason: str) -> Shop:
        """Rejects a pending shop with a mandatory rejection reason."""
        if not reason or not reason.strip():
            raise ValidationError("A non-empty rejection reason is required.")

        if shop.status != Shop.STATUS_PENDING:
            raise InvalidShopTransitionError(
                f"Cannot reject shop with status '{shop.status}'. Only PENDING shops can be rejected."
            )

        shop.status = Shop.STATUS_REJECTED
        shop.rejection_reason = reason.strip()
        shop.reviewed_by = staff_user
        shop.reviewed_at = timezone.now()
        shop.save()
        return shop

    @classmethod
    @transaction.atomic
    def suspend_shop(cls, shop: Shop, staff_user, reason: str) -> Shop:
        """Suspends an active or approved shop with a mandatory reason."""
        if not reason or not reason.strip():
            raise ValidationError("A non-empty suspension reason is required.")

        if shop.status not in (Shop.STATUS_ACTIVE, Shop.STATUS_APPROVED):
            raise InvalidShopTransitionError(
                f"Cannot suspend shop with status '{shop.status}'. Only ACTIVE or APPROVED shops can be suspended."
            )

        shop.status = Shop.STATUS_SUSPENDED
        shop.suspension_reason = reason.strip()
        shop.suspended_at = timezone.now()
        shop.save()
        return shop

    @classmethod
    @transaction.atomic
    def reactivate_shop(cls, shop: Shop, staff_user) -> Shop:
        """Reactivates a suspended shop back to ACTIVE."""
        if shop.status != Shop.STATUS_SUSPENDED:
            raise InvalidShopTransitionError(
                f"Cannot reactivate shop with status '{shop.status}'. Only SUSPENDED shops can be reactivated."
            )

        shop.status = Shop.STATUS_ACTIVE
        shop.suspension_reason = ""
        shop.save()
        return shop
