import io
import urllib.request

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from PIL import Image, ImageDraw, ImageFont

from shop.models import Category, Product, ProductImage

DEMO_PHOTO_URL = "https://picsum.photos/seed/{seed}/{size}/{size}"

CATEGORIES = [
    {"name": "Clothing", "icon": "checkroom"},
    {"name": "Electronics", "icon": "devices"},
    {"name": "Shoes", "icon": "roller_skating"},
    {"name": "Watches", "icon": "watch"},
    {"name": "Jewellery", "icon": "diamond"},
    {"name": "Health and Beauty", "icon": "spa"},
    {"name": "Kids and Babies", "icon": "child_friendly"},
    {"name": "Sports", "icon": "sports_soccer"},
    {"name": "Home and Garden", "icon": "yard"},
]

# (name, category, price, old_price, badge, stock, description, color)
PRODUCTS = [
    ("Custom Mechanical Keyboard", "Electronics", "148.00", "180.00", "NEW", 24,
     "A hot-swappable mechanical keyboard with custom keycaps, tactile switches and per-key RGB lighting.",
     (37, 99, 235)),
    ("Wireless Studio Headphones", "Electronics", "220.00", "280.00", "SALE", 15,
     "Studio-grade wireless headphones with active noise cancellation and 30-hour battery life.",
     (15, 23, 42)),
    ("Portable Bluetooth Speaker", "Electronics", "59.00", "79.00", "", 30,
     "Compact splash-resistant speaker delivering rich, room-filling sound for up to 12 hours.",
     (14, 116, 144)),
    ("Smart Fitness Tracker", "Electronics", "74.00", "", "NEW", 40,
     "Track steps, heart rate and sleep with a lightweight band and a week-long battery life.",
     (30, 64, 175)),
    ("Heavy Canvas Tote Bag", "Clothing", "38.00", "50.00", "SALE", 50,
     "A durable heavyweight canvas tote built for everyday errands and market runs.",
     (120, 53, 15)),
    ("Minimalist Cardholder", "Clothing", "48.00", "60.00", "TOP", 35,
     "Slim full-grain leather cardholder with a minimalist silhouette and RFID protection.",
     (67, 20, 7)),
    ("Organic Heavyweight Tee", "Clothing", "42.00", "55.00", "SALE", 60,
     "A soft, heavyweight tee made from 100% organic cotton with a relaxed modern fit.",
     (100, 116, 139)),
    ("Classic Denim Jacket", "Clothing", "86.00", "110.00", "", 20,
     "A timeless denim jacket with a comfortable regular fit and durable stitching.",
     (30, 58, 138)),
    ("Classic Canvas Sneakers", "Shoes", "56.00", "70.00", "SALE", 45,
     "Everyday canvas sneakers with a cushioned insole and a durable rubber outsole.",
     (220, 220, 220)),
    ("Trail Running Shoes", "Shoes", "98.00", "", "NEW", 25,
     "Lightweight trail running shoes with an aggressive grip and breathable mesh upper.",
     (185, 28, 28)),
    ("Minimalist Leather Watch", "Watches", "132.00", "165.00", "TOP", 18,
     "A minimalist watch with a genuine leather strap and a scratch-resistant sapphire crystal.",
     (66, 32, 6)),
    ("Sport Chrono Watch", "Watches", "158.00", "", "", 12,
     "A rugged chronograph watch built for daily wear with 100m water resistance.",
     (31, 41, 55)),
    ("Sterling Silver Necklace", "Jewellery", "72.00", "90.00", "SALE", 22,
     "A delicate sterling silver necklace with a hand-finished pendant.",
     (203, 213, 225)),
    ("Beaded Bracelet Set", "Jewellery", "28.00", "", "", 40,
     "A set of three stackable beaded bracelets in natural stone tones.",
     (146, 64, 14)),
    ("Natural Face Serum", "Health and Beauty", "34.00", "42.00", "SALE", 55,
     "A lightweight, fast-absorbing face serum formulated with natural botanical extracts.",
     (34, 197, 94)),
    ("Bamboo Toothbrush Set", "Health and Beauty", "16.00", "", "", 80,
     "A pack of four biodegradable bamboo toothbrushes with soft bristles.",
     (74, 222, 128)),
    ("Soft Plush Teddy Bear", "Kids and Babies", "24.00", "30.00", "TOP", 38,
     "An ultra-soft plush teddy bear, safe and huggable for children of all ages.",
     (217, 119, 6)),
    ("Kids Puzzle Set", "Kids and Babies", "19.00", "", "NEW", 42,
     "A colorful wooden puzzle set that helps develop early problem-solving skills.",
     (250, 204, 21)),
    ("Yoga Mat Premium", "Sports", "45.00", "58.00", "SALE", 33,
     "A non-slip, extra-thick yoga mat with excellent cushioning for every practice.",
     (79, 70, 229)),
    ("Adjustable Dumbbell Set", "Sports", "120.00", "", "", 10,
     "A space-saving adjustable dumbbell set that replaces a full rack of weights.",
     (55, 65, 81)),
    ("Insulated Flask 750ml", "Home and Garden", "34.00", "45.00", "HOT", 48,
     "A vacuum-insulated stainless steel flask that keeps drinks cold or hot for 24 hours.",
     (8, 145, 178)),
    ("Artisan Ceramic Mug", "Home and Garden", "26.00", "32.00", "", 60,
     "A handcrafted ceramic mug with a matte glaze finish, perfect for coffee or tea.",
     (194, 65, 12)),
    ("Task Desk Lamp", "Home and Garden", "89.00", "110.00", "NEW", 20,
     "A dimmable LED desk lamp with an adjustable arm and a built-in USB charging port.",
     (250, 204, 21)),
    ("Indoor Plant Pot Set", "Home and Garden", "32.00", "", "", 44,
     "A set of three minimalist ceramic plant pots with drainage holes and trays.",
     (34, 197, 94)),
]


def shade_color(color, factor):
    r, g, b = color
    if factor >= 0:
        r, g, b = (channel + (255 - channel) * factor for channel in (r, g, b))
    else:
        r, g, b = (channel * (1 + factor) for channel in (r, g, b))
    return tuple(max(0, min(255, int(channel))) for channel in (r, g, b))


GALLERY_SHADE_FACTORS = (0.3, -0.25, 0.55)


def generate_placeholder_image(label, color):
    image = Image.new("RGB", (800, 800), color=color)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    words = label.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > 16:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)

    line_height = 22
    total_height = line_height * len(lines)
    y = (800 - total_height) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (800 - text_width) // 2
        draw.text((x, y), line, fill="white", font=font)
        y += line_height

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return ContentFile(buffer.getvalue())


def build_product_photo(label, color, seed):
    # Real photos make the demo UI look right; fall back to a drawn placeholder
    # whenever the network/service is unavailable (offline dev, CI, outages).
    try:
        request = urllib.request.Request(
            DEMO_PHOTO_URL.format(seed=seed, size=800),
            headers={"User-Agent": "MiniShop-DemoSeeder/1.0"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            return ContentFile(response.read()), "jpg"
    except Exception:
        return generate_placeholder_image(label, color), "png"


class Command(BaseCommand):
    help = "Seed the database with demo categories and products."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Replace images for products/gallery that already exist.",
        )

    def set_cover_image(self, product, name, color, slug):
        photo, ext = build_product_photo(name, color, slug)
        product.image.save(f"{slug}.{ext}", photo, save=False)

    def add_gallery_image(self, product, name, color, slug, index, factor):
        seed = f"{slug}-{index}"
        photo, ext = build_product_photo(f"{name} {index + 1}", shade_color(color, factor), seed)
        gallery_image = ProductImage(product=product, order=index)
        gallery_image.image.save(f"{slug}-{index}.{ext}", photo, save=False)
        gallery_image.save()

    def handle(self, *args, **options):
        force = options["force"]
        categories_by_name = {}
        for entry in CATEGORIES:
            category, created = Category.objects.get_or_create(
                slug=slugify(entry["name"]),
                defaults={"name": entry["name"], "icon": entry["icon"]},
            )
            categories_by_name[entry["name"]] = category
            self.stdout.write(f"{'Created' if created else 'Exists'} category: {category.name}")

        for name, cat_name, price, old_price, badge, stock, description, color in PRODUCTS:
            slug = slugify(name)
            product = Product.objects.filter(slug=slug).first()

            if product is None:
                product = Product(
                    name=name,
                    slug=slug,
                    category=categories_by_name[cat_name],
                    description=description,
                    price=price,
                    old_price=old_price or None,
                    stock=stock,
                    badge=badge,
                )
                self.set_cover_image(product, name, color, slug)
                product.save()
                self.stdout.write(f"Created product: {name}")
            else:
                self.stdout.write(f"Exists product: {name}")
                if force:
                    product.image.delete(save=False)
                    self.set_cover_image(product, name, color, slug)
                    product.save()
                    self.stdout.write("  Replaced cover image")

            if force or not product.images.exists():
                for old_image in product.images.all():
                    old_image.image.delete(save=False)
                product.images.all().delete()
                for index, factor in enumerate(GALLERY_SHADE_FACTORS, start=1):
                    self.add_gallery_image(product, name, color, slug, index, factor)
                self.stdout.write(f"  Set {len(GALLERY_SHADE_FACTORS)} gallery images")

        self.stdout.write(self.style.SUCCESS("Demo data seeding complete."))
