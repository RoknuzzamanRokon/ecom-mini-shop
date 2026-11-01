import type {
  AdminOnboardedProductDetail,
  AdminOnboardingSellerDetail,
  AdminOnboardingShop,
} from "@/lib/admin-api";
import { changedFields, phoneList } from "./editSession";
import type { EditField, EditResult, EditValues } from "./EditDialog";

export interface EditForm {
  fields: EditField[];
  initial: EditValues;
  toChanges: (draft: EditValues) => EditResult;
}

const text = (value: string | boolean | undefined) => String(value ?? "").trim();

/** OnboardingSellerUpdateSerializer: the business details. The type and the login stay as they are. */
export function sellerForm(seller: AdminOnboardingSellerDetail): EditForm {
  const initial = {
    business_name: seller.business_name,
    business_phone: seller.business_phone,
    business_email: seller.business_email,
    tax_id: seller.tax_id,
    description: seller.description,
  };
  return {
    fields: [
      { name: "business_name", label: "Business name" },
      { name: "business_phone", label: "Business phone", inputMode: "tel" },
      { name: "business_email", label: "Business email", inputMode: "email" },
      { name: "tax_id", label: "Tax ID" },
      { name: "description", label: "Description", kind: "textarea" },
    ],
    initial,
    toChanges: (draft) => {
      const next = {
        business_name: text(draft.business_name),
        business_phone: text(draft.business_phone),
        business_email: text(draft.business_email),
        tax_id: text(draft.tax_id),
        description: text(draft.description),
      };
      if (!next.business_name) return { error: "The business needs a name." };
      return { changes: changedFields(initial, next) };
    },
  };
}

/** OnboardingShopUpdateSerializer: profile, phones and location (latitude and longitude together). */
export function shopForm(shop: AdminOnboardingShop): EditForm {
  const initial = {
    name: shop.name,
    phone: shop.phone,
    additional_phones: shop.additional_phones.join(", "),
    address: shop.address,
    description: shop.description,
    latitude: shop.latitude === null ? "" : String(shop.latitude),
    longitude: shop.longitude === null ? "" : String(shop.longitude),
  };
  return {
    fields: [
      { name: "name", label: "Shop name" },
      { name: "phone", label: "Phone", inputMode: "tel" },
      { name: "additional_phones", label: "More phones", inputMode: "tel", hint: "Separate numbers with commas." },
      { name: "address", label: "Address", kind: "textarea" },
      { name: "description", label: "Description", kind: "textarea" },
      { name: "latitude", label: "Latitude", inputMode: "decimal" },
      { name: "longitude", label: "Longitude", inputMode: "decimal" },
    ],
    initial,
    toChanges: (draft) => {
      const name = text(draft.name);
      if (!name) return { error: "The shop needs a name." };
      const changes: Record<string, unknown> = changedFields(
        { name: initial.name, phone: initial.phone, address: initial.address, description: initial.description },
        { name, phone: text(draft.phone), address: text(draft.address), description: text(draft.description) }
      );
      const phones = phoneList(text(draft.additional_phones));
      if (JSON.stringify(phones) !== JSON.stringify(shop.additional_phones)) changes.additional_phones = phones;

      const latitude = text(draft.latitude);
      const longitude = text(draft.longitude);
      if (latitude !== initial.latitude || longitude !== initial.longitude) {
        const lat = Number(latitude);
        const lng = Number(longitude);
        if (!latitude || !longitude || Number.isNaN(lat) || Number.isNaN(lng)) {
          return { error: "Enter both latitude and longitude as numbers." };
        }
        changes.latitude = lat;
        changes.longitude = lng;
      }
      return { changes };
    },
  };
}

const MONEY = /^\d+(\.\d{1,2})?$/;

/**
 * OnboardingProductUpdateSerializer. A new stock is sent with the figure it
 * was edited from, so units sold meanwhile are not put back on sale.
 */
export function productForm(product: AdminOnboardedProductDetail): EditForm {
  const initial = {
    name: product.name,
    price: product.price,
    old_price: product.old_price ?? "",
    stock: String(product.stock),
    badge: product.badge,
    description: product.description,
    is_active: product.is_active,
  };
  return {
    fields: [
      { name: "name", label: "Product name" },
      { name: "price", label: "Price (৳)", inputMode: "decimal" },
      { name: "old_price", label: "Old price (৳)", inputMode: "decimal", hint: "Leave empty for no crossed-out price." },
      { name: "stock", label: "Stock", inputMode: "numeric" },
      { name: "badge", label: "Badge", hint: "Up to 20 characters, e.g. New." },
      { name: "description", label: "Description", kind: "textarea" },
      { name: "is_active", label: "Shown to customers", kind: "checkbox" },
    ],
    initial,
    toChanges: (draft) => {
      const name = text(draft.name);
      const price = text(draft.price);
      const oldPrice = text(draft.old_price);
      const stock = text(draft.stock);
      if (!name) return { error: "The product needs a name." };
      if (!MONEY.test(price) || Number(price) <= 0) return { error: "Enter a price above ৳0, e.g. 450 or 450.50." };
      if (oldPrice && (!MONEY.test(oldPrice) || Number(oldPrice) <= 0)) {
        return { error: "Enter the old price as an amount above ৳0, or leave it empty." };
      }
      if (!/^\d+$/.test(stock)) return { error: "Enter the stock as a whole number." };
      if (text(draft.badge).length > 20) return { error: "A badge is at most 20 characters." };

      const changes: Record<string, unknown> = changedFields(
        { name: initial.name, badge: initial.badge, description: initial.description, is_active: initial.is_active },
        { name, badge: text(draft.badge), description: text(draft.description), is_active: Boolean(draft.is_active) }
      );
      if (Number(price) !== Number(initial.price)) changes.price = price;
      if (oldPrice !== text(initial.old_price) && Number(oldPrice) !== Number(initial.old_price)) {
        changes.old_price = oldPrice || null;
      }
      if (Number(stock) !== product.stock) {
        changes.stock = Number(stock);
        changes.expected_stock = product.stock;
      }
      return { changes };
    },
  };
}
