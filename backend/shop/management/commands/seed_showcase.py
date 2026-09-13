from decimal import Decimal
import urllib.request

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from rbac.models import Role, UserRole
from sellers.models import SellerProfile
from shop.management.commands.seed_demo_data import generate_placeholder_image
from shop.models import Category, Product, ProductImage, ProductInventory
from shops.fields import Point
from shops.models import Shop

UNSPLASH_URL = "https://images.unsplash.com/{photo_id}?auto=format&q=80&fit=crop&crop={crop}&w={width}&h={height}"
FLICKR_URL = "https://loremflickr.com/{width}/{height}/{keyword}"

SELLER_ROLE_CODE = "SALES_TEAM"

# (name, icon, photo_id, keyword, description)
CATEGORIES = [
    ("Clothing", "checkroom", "photo-1445205170230-053b83016050", "clothing-store",
     "Carefully curated essentials designed for everyday comfort, timeless modern silhouettes, and architectural elegance."),
    ("Electronics", "devices", "photo-1498049794561-7780e7231661", "electronics",
     "Cutting-edge audio, custom mechanical keyboards, smart wearable fitness trackers, and modern everyday workspace gear."),
    ("Shoes", "roller_skating", "photo-1549298916-b41d501d3772", "sneakers",
     "Everyday cushioned canvas sneakers, lightweight trail runners, and versatile footwear built for modern motion."),
    ("Watches", "watch", "photo-1434056886845-dac89ffe9b56", "wristwatch",
     "Precision timepieces featuring genuine leather straps, scratch-resistant sapphire crystals, and chronograph detailing."),
    ("Jewellery", "diamond", "photo-1601121141461-9d6647bca1ed", "jewellery",
     "Delicate sterling silver necklaces, hand-finished pendants, and natural stone beaded bracelet sets for all occasions."),
    ("Health and Beauty", "spa", "photo-1596462502278-27bfdc403348", "skincare",
     "Clean botanical face serums, natural bamboo grooming essentials, and restorative wellness care for everyday vitality."),
    ("Kids and Babies", "child_friendly", "photo-1515488042361-ee00e0ddd4e4", "toys",
     "Ultra-soft gentle cotton essentials, playful educational puzzle sets, and cuddly plush toys made for curious minds."),
    ("Sports", "sports_soccer", "photo-1517836357463-d25dfeac3438", "fitness",
     "High-performance workout equipment, premium studio yoga mats, and durable athletic gear built for an active lifestyle."),
    ("Home and Garden", "yard", "photo-1416879595882-3373a0480b5b", "home-decor",
     "Elevate your indoor spaces with artisan ceramic mugs, modern planters, cozy desk lamps, and architectural decor."),
]

SHOPS = [
    {
        "slug": "technest-electronics",
        "name": "TechNest Electronics",
        "username": "technest_seller",
        "email": "technest@minishop.demo",
        "business_name": "TechNest Electronics Ltd.",
        "description": "Dhaka's trusted destination for studio audio gear, custom mechanical keyboards and everyday smart tech. Every unit ships with a genuine one-year warranty and same-day servicing.",
        "phone": "+880 1711-345678",
        "address": "Shop 402, Level 4, Bashundhara City Shopping Complex, Panthapath, Dhaka 1215",
        "longitude": 90.3896,
        "latitude": 23.7509,
        "cover": ("photo-1441986300917-64674bd600d8", "electronics-store"),
        "logo": ("photo-1505740420928-5e560c06d30e", "headphones"),
    },
    {
        "slug": "urban-thread",
        "name": "Urban Thread",
        "username": "urbanthread_seller",
        "email": "urbanthread@minishop.demo",
        "business_name": "Urban Thread Fashion House",
        "description": "Contemporary everyday wear, full-grain leather goods and sneakers built for Dhaka streets. Ethically sourced fabrics, honest pricing, free exchanges within seven days.",
        "phone": "+880 1819-556677",
        "address": "House 27, Road 11, Banani, Dhaka 1213",
        "longitude": 90.4043,
        "latitude": 23.7936,
        "cover": ("photo-1567401893414-76b7b1e5a7a5", "clothing-boutique"),
        "logo": ("photo-1525966222134-fcfa99b8ae77", "sneakers"),
    },
    {
        "slug": "bloom-and-home",
        "name": "Bloom & Home",
        "username": "bloomhome_seller",
        "email": "bloomhome@minishop.demo",
        "business_name": "Bloom & Home Living",
        "description": "Handcrafted ceramics, minimalist planters and warm task lighting for calm, considered interiors. Each piece is finished by local artisans in small batches.",
        "phone": "+880 1911-778899",
        "address": "Plot 14, Old Dhanmondi 27, Dhanmondi, Dhaka 1209",
        "longitude": 90.3742,
        "latitude": 23.7461,
        "cover": ("photo-1555041469-a586c61ea9bc", "home-decor-store"),
        "logo": ("photo-1514228742587-6b1558fcca3d", "ceramic-mug"),
    },
    {
        "slug": "vitalcare-essentials",
        "name": "VitalCare Essentials",
        "username": "vitalcare_seller",
        "email": "vitalcare@minishop.demo",
        "business_name": "VitalCare Essentials",
        "description": "Clean skincare, family wellness and home fitness essentials sourced from certified suppliers. Batch numbers and expiry dates are verified on every incoming shipment.",
        "phone": "+880 1670-223344",
        "address": "Level 2, Jamuna Future Park, Kuril, Dhaka 1229",
        "longitude": 90.4254,
        "latitude": 23.8133,
        "cover": ("photo-1584308666744-24d5c474f2ae", "pharmacy-store"),
        "logo": ("photo-1620916566398-39f1143ab7be", "face-serum"),
    },
]

# (name, shop_slug, category, price, old_price, badge, stock, description, photo_id, keyword)
PRODUCTS = [
    ("Custom Mechanical Keyboard", "technest-electronics", "Electronics", "12500.00", "15900.00", "NEW", 24,
     "A hot-swappable mechanical keyboard with custom PBT keycaps, tactile switches and per-key RGB lighting.",
     "photo-1587829741301-dc798b83add3", "mechanical-keyboard"),
    ("Wireless Studio Headphones", "technest-electronics", "Electronics", "18900.00", "23500.00", "SALE", 15,
     "Studio-grade wireless headphones with active noise cancellation and 30-hour battery life.",
     "photo-1505740420928-5e560c06d30e", "headphones"),
    ("Portable Bluetooth Speaker", "technest-electronics", "Electronics", "4950.00", "6400.00", "", 30,
     "Compact splash-resistant speaker delivering rich, room-filling sound for up to 12 hours.",
     "photo-1608043152269-423dbba4e7e1", "bluetooth-speaker"),
    ("Smart Fitness Tracker", "technest-electronics", "Electronics", "6200.00", "", "NEW", 40,
     "Track steps, heart rate and sleep with a lightweight band and a week-long battery life.",
     "photo-1575311373937-040b8e1fd5b6", "fitness-tracker"),
    ("Minimalist Leather Watch", "technest-electronics", "Watches", "11200.00", "13900.00", "TOP", 18,
     "A minimalist watch with a genuine leather strap and a scratch-resistant sapphire crystal.",
     "photo-1524592094714-0f0654e20314", "leather-watch"),
    ("Sport Chrono Watch", "technest-electronics", "Watches", "13400.00", "", "", 12,
     "A rugged chronograph watch built for daily wear with 100m water resistance.",
     "photo-1533139502658-0198f920d8e8", "chronograph-watch"),

    ("Heavy Canvas Tote Bag", "urban-thread", "Clothing", "1450.00", "1890.00", "SALE", 50,
     "A durable heavyweight canvas tote built for everyday errands and market runs.",
     "photo-1591561954557-26941169b49e", "tote-bag"),
    ("Minimalist Cardholder", "urban-thread", "Clothing", "1950.00", "2400.00", "TOP", 35,
     "Slim full-grain leather cardholder with a minimalist silhouette and RFID protection.",
     "photo-1627123424574-724758594e93", "leather-wallet"),
    ("Organic Heavyweight Tee", "urban-thread", "Clothing", "1290.00", "1690.00", "SALE", 60,
     "A soft, heavyweight tee made from 100% organic cotton with a relaxed modern fit.",
     "photo-1521572163474-6864f9cf17ab", "tshirt"),
    ("Classic Denim Jacket", "urban-thread", "Clothing", "3850.00", "4900.00", "", 20,
     "A timeless denim jacket with a comfortable regular fit and durable stitching.",
     "photo-1543076447-215ad9ba6923", "denim-jacket"),
    ("Classic Canvas Sneakers", "urban-thread", "Shoes", "2650.00", "3300.00", "SALE", 45,
     "Everyday canvas sneakers with a cushioned insole and a durable rubber outsole.",
     "photo-1525966222134-fcfa99b8ae77", "canvas-sneakers"),
    ("Trail Running Shoes", "urban-thread", "Shoes", "5900.00", "", "NEW", 25,
     "Lightweight trail running shoes with an aggressive grip and breathable mesh upper.",
     "photo-1542291026-7eec264c27ff", "running-shoes"),
    ("Sterling Silver Necklace", "urban-thread", "Jewellery", "3400.00", "4200.00", "SALE", 22,
     "A delicate sterling silver necklace with a hand-finished pendant.",
     "photo-1515562141207-7a88fb7ce338", "silver-necklace"),
    ("Beaded Bracelet Set", "urban-thread", "Jewellery", "1150.00", "", "", 40,
     "A set of three stackable beaded bracelets in natural stone tones.",
     "photo-1611591437281-460bfbe1220a", "bracelet"),

    ("Insulated Flask 750ml", "bloom-and-home", "Home and Garden", "1690.00", "2150.00", "HOT", 48,
     "A vacuum-insulated stainless steel flask that keeps drinks cold or hot for 24 hours.",
     "photo-1602143407151-7111542de6e8", "water-bottle"),
    ("Artisan Ceramic Mug", "bloom-and-home", "Home and Garden", "890.00", "1150.00", "", 60,
     "A handcrafted ceramic mug with a matte glaze finish, perfect for coffee or tea.",
     "photo-1514228742587-6b1558fcca3d", "ceramic-mug"),
    ("Task Desk Lamp", "bloom-and-home", "Home and Garden", "3250.00", "3990.00", "NEW", 20,
     "A dimmable LED desk lamp with an adjustable arm and a built-in USB charging port.",
     "photo-1507473885765-e6ed057f782c", "desk-lamp"),
    ("Indoor Plant Pot Set", "bloom-and-home", "Home and Garden", "1480.00", "", "", 44,
     "A set of three minimalist ceramic plant pots with drainage holes and matching trays.",
     "photo-1485955900006-10f4d324d411", "plant-pot"),

    ("Natural Face Serum", "vitalcare-essentials", "Health and Beauty", "1850.00", "2300.00", "SALE", 55,
     "A lightweight, fast-absorbing face serum formulated with natural botanical extracts.",
     "photo-1620916566398-39f1143ab7be", "face-serum"),
    ("Bamboo Toothbrush Set", "vitalcare-essentials", "Health and Beauty", "640.00", "", "", 80,
     "A pack of four biodegradable bamboo toothbrushes with soft charcoal-infused bristles.",
     "photo-1607613009820-a29f7bb81c04", "bamboo-toothbrush"),
    ("Soft Plush Teddy Bear", "vitalcare-essentials", "Kids and Babies", "1250.00", "1590.00", "TOP", 38,
     "An ultra-soft plush teddy bear, safe and huggable for children of all ages.",
     "photo-1559454403-b8fb88521f11", "teddy-bear"),
    ("Kids Puzzle Set", "vitalcare-essentials", "Kids and Babies", "950.00", "", "NEW", 42,
     "A colorful wooden puzzle set that helps develop early problem-solving skills.",
     "photo-1516981879613-9f5da904015f", "puzzle"),
    ("Yoga Mat Premium", "vitalcare-essentials", "Sports", "2400.00", "2950.00", "SALE", 33,
     "A non-slip, extra-thick yoga mat with excellent cushioning for every practice.",
     "photo-1601925260368-ae2f83cf8b7f", "yoga-mat"),
    ("Adjustable Dumbbell Set", "vitalcare-essentials", "Sports", "8900.00", "", "", 10,
     "A space-saving adjustable dumbbell set that replaces a full rack of fixed weights.",
     "photo-1638536532686-d610adfc8e5c", "dumbbell"),
]

# Re-crops of the same source photo stand in for alternate product shots.
GALLERY_VARIANTS = [
    {"crop": "edges", "width": 900, "height": 900},
    {"crop": "entropy", "width": 1200, "height": 900},
]


def download(url, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": "MiniShop-ShowcaseSeeder/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_photo(photo_id, keyword, width=900, height=900, crop="entropy"):
    """Real photo first, keyword photo next, drawn placeholder as the offline fallback."""
    candidates = [
        UNSPLASH_URL.format(photo_id=photo_id, crop=crop, width=width, height=height),
        FLICKR_URL.format(width=width, height=height, keyword=keyword),
    ]
    for url in candidates:
        try:
            data = download(url)
        except Exception:
            continue
        if data:
            return ContentFile(data), "jpg"
    return generate_placeholder_image(keyword.replace("-", " ").title(), (71, 85, 105)), "png"


def file_missing(field):
    if not field or not field.name:
        return True
    try:
        return not field.storage.exists(field.name)
    except Exception:
        return True


class Command(BaseCommand):
    help = "Seed a presentable multi-shop demo storefront with real product photography."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-download images even when the files already exist on disk.",
        )
        parser.add_argument(
            "--password",
            default="",
            help="Optional login password for the demo seller accounts (local development only).",
        )

    def assign_image(self, field, filename, photo_id, keyword, force, **photo_kwargs):
        if not (force or file_missing(field)):
            return False
        content, ext = fetch_photo(photo_id, keyword, **photo_kwargs)
        if field and field.name:
            field.delete(save=False)
        field.save(f"{filename}.{ext}", content, save=False)
        return True

    def seed_categories(self, force):
        categories = {}
        for name, icon, photo_id, keyword, description in CATEGORIES:
            category, created = Category.objects.get_or_create(
                slug=slugify(name),
                defaults={"name": name, "icon": icon, "description": description},
            )
            category.icon = category.icon or icon
            category.description = category.description or description
            category.is_active = True
            downloaded = self.assign_image(
                category.image, slugify(name), photo_id, keyword, force, width=1200, height=800,
            )
            category.save()
            categories[name] = category
            self.stdout.write(
                f"  {'created' if created else 'updated'} category {name}"
                f"{' (photo downloaded)' if downloaded else ''}"
            )
        return categories

    def seed_shops(self, force, password):
        User = get_user_model()
        seller_role = Role.objects.filter(code=SELLER_ROLE_CODE).first()
        shops = {}

        for entry in SHOPS:
            user, user_created = User.objects.get_or_create(
                username=entry["username"],
                defaults={"email": entry["email"], "first_name": entry["name"]},
            )
            if user_created:
                if password:
                    user.set_password(password)
                else:
                    user.set_unusable_password()
                user.save()
            elif password:
                user.set_password(password)
                user.save()

            if seller_role:
                UserRole.objects.get_or_create(user=user, role=seller_role)

            seller, _ = SellerProfile.objects.get_or_create(
                user=user,
                defaults={
                    "business_name": entry["business_name"],
                    "business_email": entry["email"],
                    "business_phone": entry["phone"],
                    "description": entry["description"],
                },
            )
            if seller.status != SellerProfile.STATUS_ACTIVE:
                seller.status = SellerProfile.STATUS_ACTIVE
                seller.approved_at = seller.approved_at or timezone.now()
                seller.save()

            shop, shop_created = Shop.objects.get_or_create(
                slug=entry["slug"],
                defaults={"owner": seller, "name": entry["name"]},
            )
            shop.owner = seller
            shop.name = entry["name"]
            shop.description = entry["description"]
            shop.phone = entry["phone"]
            shop.address = entry["address"]
            shop.location = Point(entry["longitude"], entry["latitude"])
            shop.status = Shop.STATUS_ACTIVE
            shop.approved_at = shop.approved_at or timezone.now()

            logo_id, logo_keyword = entry["logo"]
            cover_id, cover_keyword = entry["cover"]
            self.assign_image(
                shop.logo, f"{entry['slug']}-logo", logo_id, logo_keyword, force, width=400, height=400,
            )
            self.assign_image(
                shop.cover_image, f"{entry['slug']}-cover", cover_id, cover_keyword, force,
                width=1600, height=600, crop="edges",
            )
            shop.save()
            shops[entry["slug"]] = shop
            self.stdout.write(
                f"  {'created' if shop_created else 'updated'} shop {shop.name} "
                f"({shop.address.split(',')[-1].strip()})"
            )
        return shops

    def seed_gallery(self, product, photo_id, keyword, force):
        existing = list(product.images.all())
        # Gallery rows can outlive their files (media/ is gitignored, the database is shared),
        # so a row count alone is not proof the images still render.
        intact = len(existing) >= len(GALLERY_VARIANTS) and not any(
            file_missing(image.image) for image in existing
        )
        if intact and not force:
            return
        for image in existing:
            image.image.delete(save=False)
        product.images.all().delete()
        for index, variant in enumerate(GALLERY_VARIANTS, start=1):
            content, ext = fetch_photo(photo_id, keyword, **variant)
            gallery_image = ProductImage(product=product, order=index)
            gallery_image.image.save(f"{product.slug}-{index}.{ext}", content, save=False)
            gallery_image.save()

    def seed_products(self, categories, shops, force):
        for (name, shop_slug, category_name, price, old_price, badge, stock,
             description, photo_id, keyword) in PRODUCTS:
            slug = slugify(name)
            product = Product.objects.filter(slug=slug).first() or Product(name=name, slug=slug)

            product.name = name
            product.category = categories[category_name]
            product.shop = shops[shop_slug]
            product.description = description
            product.price = Decimal(price)
            product.old_price = Decimal(old_price) if old_price else None
            product.stock = stock
            product.badge = badge
            product.is_active = True
            product.status = Product.STATUS_PUBLISHED

            downloaded = self.assign_image(product.image, slug, photo_id, keyword, force)
            product.save()

            self.seed_gallery(product, photo_id, keyword, force)

            inventory, _ = ProductInventory.objects.get_or_create(product=product)
            if inventory.available_quantity != stock:
                inventory.available_quantity = stock
                inventory.save()

            self.stdout.write(
                f"  {name} -> {shops[shop_slug].name} (BDT {price})"
                f"{' (photo downloaded)' if downloaded else ''}"
            )

    def handle(self, *args, **options):
        force = options["force"]
        password = options["password"]

        self.stdout.write("Categories")
        categories = self.seed_categories(force)

        self.stdout.write("Shops")
        shops = self.seed_shops(force, password)

        self.stdout.write("Products")
        self.seed_products(categories, shops, force)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Showcase ready: {len(shops)} shops, {len(categories)} categories, {len(PRODUCTS)} products."
        ))
        if password:
            self.stdout.write(self.style.WARNING(
                "Demo seller accounts share the password you supplied - local development only."
            ))
        else:
            self.stdout.write(
                "Demo seller accounts have no usable password. Pass --password to enable seller login."
            )
