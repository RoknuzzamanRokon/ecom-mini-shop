from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import CanUpdateCart, CanViewCart
from .serializers import (
    CartItemCreateSerializer,
    CartItemSerializer,
    CartItemUpdateSerializer,
    CartSerializer,
)
from .services import CartService


class CartView(APIView):
    """
    Endpoints for the current authenticated user's cart.
    GET: Retrieves the user's cart, items, live prices, and totals.
    DELETE: Clears all items from the user's cart.
    """
    def get_permissions(self):
        if self.request.method == "DELETE":
            return [permissions.IsAuthenticated(), CanUpdateCart()]
        return [permissions.IsAuthenticated(), CanViewCart()]

    def get(self, request):
        cart = CartService.get_cart_with_items(request.user)
        serializer = CartSerializer(cart, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request):
        CartService.clear_cart(request.user)
        return Response(
            {"detail": "Cart cleared successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )


class CartItemCreateView(APIView):
    """
    Endpoint for adding products to the current authenticated user's cart.
    POST /api/cart/items/
    """
    permission_classes = [permissions.IsAuthenticated, CanUpdateCart]

    def post(self, request):
        serializer = CartItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        CartService.add_item(
            user=request.user,
            product_id=serializer.validated_data["product_id"],
            quantity=serializer.validated_data.get("quantity", 1),
        )

        cart = CartService.get_cart_with_items(request.user)
        return Response(
            CartSerializer(cart, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class CartItemDetailView(APIView):
    """
    Endpoints for managing a specific item in the current user's cart.
    PATCH /api/cart/items/<id>/: Updates quantity.
    DELETE /api/cart/items/<id>/: Removes item from cart.
    """
    permission_classes = [permissions.IsAuthenticated, CanUpdateCart]

    def patch(self, request, pk):
        serializer = CartItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        CartService.update_item_quantity(
            user=request.user,
            item_id=pk,
            quantity=serializer.validated_data["quantity"],
        )

        cart = CartService.get_cart_with_items(request.user)
        return Response(
            CartSerializer(cart, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        CartService.remove_item(user=request.user, item_id=pk)

        cart = CartService.get_cart_with_items(request.user)
        return Response(
            CartSerializer(cart, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )
