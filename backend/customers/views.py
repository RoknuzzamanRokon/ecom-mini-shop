from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Address, Favorite
from .permissions import (
    CanCreateAddress,
    CanDeleteAddress,
    CanUpdateAddress,
    CanUpdateProfile,
    CanViewAddress,
    CanViewProfile,
    IsAddressOwner,
)
from .serializers import (
    AddressCreateUpdateSerializer,
    AddressSerializer,
    CustomerProfileSerializer,
    CustomerProfileUpdateSerializer,
    FavoriteCreateSerializer,
    FavoriteSerializer,
)
from .services import AddressService, CustomerService


class CustomerProfileView(APIView):
    """
    Self-service endpoint for inspecting and updating the authenticated user's profile.
    GET /api/profile/me/
    PATCH /api/profile/me/
    """

    def get_permissions(self):
        if self.request.method in ["PATCH", "PUT"]:
            return [IsAuthenticated(), CanUpdateProfile()]
        return [IsAuthenticated(), CanViewProfile()]

    def get(self, request):
        profile = CustomerService.get_or_create_profile(request.user)
        serializer = CustomerProfileSerializer(profile, context={"request": request})
        return Response(serializer.data)

    def patch(self, request):
        profile = CustomerService.get_or_create_profile(request.user)
        serializer = CustomerProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_profile = CustomerService.update_profile(
            user=request.user,
            data=serializer.validated_data,
            actor=request.user,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        return Response(
            CustomerProfileSerializer(updated_profile, context={"request": request}).data
        )

    def put(self, request):
        return self.patch(request)


class AddressListCreateView(APIView):
    """
    List and create endpoints for the authenticated user's address book.
    GET /api/addresses/
    POST /api/addresses/
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), CanCreateAddress()]
        return [IsAuthenticated(), CanViewAddress()]

    def get(self, request):
        addresses = Address.objects.filter(user=request.user).order_by(
            "-is_default", "-created_at"
        )
        serializer = AddressSerializer(addresses, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = AddressCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = AddressService.create_address(
            user=request.user,
            data=serializer.validated_data,
            actor=request.user,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        return Response(AddressSerializer(address).data, status=status.HTTP_201_CREATED)


class AddressDetailView(APIView):
    """
    Detail endpoint to retrieve, modify, or remove an individual address.
    GET /api/addresses/<id>/
    PATCH /api/addresses/<id>/
    DELETE /api/addresses/<id>/
    """

    def get_permissions(self):
        if self.request.method in ["PATCH", "PUT"]:
            return [IsAuthenticated(), CanUpdateAddress(), IsAddressOwner()]
        if self.request.method == "DELETE":
            return [IsAuthenticated(), CanDeleteAddress(), IsAddressOwner()]
        return [IsAuthenticated(), CanViewAddress(), IsAddressOwner()]

    def get_object(self, pk):
        address = get_object_or_404(Address, pk=pk)
        self.check_object_permissions(self.request, address)
        return address

    def get(self, request, pk):
        address = self.get_object(pk)
        return Response(AddressSerializer(address).data)

    def patch(self, request, pk):
        address = self.get_object(pk)
        serializer = AddressCreateUpdateSerializer(address, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_address = AddressService.update_address(
            address=address,
            data=serializer.validated_data,
            actor=request.user,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        return Response(AddressSerializer(updated_address).data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        address = self.get_object(pk)
        AddressService.delete_address(
            address=address,
            actor=request.user,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        return Response(
            {"detail": "Address deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )


class AddressSetDefaultView(APIView):
    """
    Action endpoint to explicitly promote an address to default.
    POST /api/addresses/<id>/set-default/
    """
    permission_classes = [IsAuthenticated, CanUpdateAddress, IsAddressOwner]

    def post(self, request, pk):
        address = get_object_or_404(Address, pk=pk)
        self.check_object_permissions(request, address)
        updated_address = AddressService.set_default_address(
            address=address,
            actor=request.user,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        return Response(AddressSerializer(updated_address).data, status=status.HTTP_200_OK)


class FavoriteListCreateView(APIView):
    """
    Wishlist endpoints for the authenticated customer.
    GET  /api/favorites/
    POST /api/favorites/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        favorites = (
            Favorite.objects.filter(user=request.user)
            .select_related("product", "product__category", "product__shop")
            .order_by("-created_at")
        )
        serializer = FavoriteSerializer(favorites, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        serializer = FavoriteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        favorite, created = Favorite.objects.get_or_create(
            user=request.user,
            product_id=serializer.validated_data["product_id"],
        )
        return Response(
            FavoriteSerializer(favorite, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class FavoriteDetailView(APIView):
    """
    Removes a product from the authenticated customer's wishlist.
    DELETE /api/favorites/<product_id>/
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, product_id):
        deleted, _ = Favorite.objects.filter(
            user=request.user, product_id=product_id
        ).delete()
        if not deleted:
            return Response(
                {"detail": "Favorite not found."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
