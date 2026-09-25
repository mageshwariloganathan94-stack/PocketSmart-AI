import os
import json
import re
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# We import genai conditionally or handle import errors gracefully
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

def get_gemini_client():
    """Initializes and returns the official Google GenAI client if API key is present."""
    if genai is None:
        return None
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"Error initializing Gemini client: {e}")
        return None

def get_platform_search_url(platform: str, item_name: str) -> str:
    """Generates standard platform search URLs without scraping."""
    clean_query = urllib.parse.quote_plus(item_name.strip())
    p = platform.lower()
    if "ikea" in p:
        return f"https://www.ikea.com/in/en/search/?q={clean_query}"
    elif "amazon" in p:
        return f"https://www.amazon.in/s?k={clean_query}"
    elif "flipkart" in p:
        return f"https://www.flipkart.com/search?q={clean_query}"
    elif "swiggy" in p:
        return f"https://www.swiggy.com/search?query={clean_query}"
    elif "zomato" in p:
        return f"https://www.zomato.com/search?q={clean_query}"
    elif "oyo" in p:
        return f"https://www.oyorooms.com/search?query={clean_query}"
    else:
        return f"https://www.amazon.in/s?k={clean_query}"

def clean_and_parse_json(text: str) -> Optional[Any]:
    """Safely extracts and parses JSON from Gemini text response."""
    if not text:
        return None
    
    # Strip markdown code blocks ```json ... ```
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    
    # Regex fallback for first [ ... ] or { ... }
    list_match = re.search(r"(\[\s*\{.*\}\s*\])", cleaned, flags=re.DOTALL)
    if list_match:
        try:
            return json.loads(list_match.group(1))
        except Exception:
            pass
            
    obj_match = re.search(r"(\{\s*\".*\"\s*:.*\})", cleaned, flags=re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(1))
        except Exception:
            pass

    return None

def enforce_budget_limit(
    items: List[Dict[str, Any]], 
    max_budget: float
) -> Tuple[List[Dict[str, Any]], float]:
    """Ensures total estimated price strictly does not exceed max_budget."""
    if not items or max_budget <= 0:
        return items, 0.0

    total = sum(float(item.get("estimated_price", 0)) for item in items)
    
    # If already within budget, keep prices
    if total <= max_budget and total > 0:
        # Standardize links
        for it in items:
            it["product_search_link"] = get_platform_search_url(
                it.get("platform", "Amazon"), 
                it.get("item_name", "item")
            )
            it["estimated_price"] = round(float(it["estimated_price"]), 2)
        return items, round(total, 2)
    
    # If exceeded, scale proportionally so sum equals ~95% of max_budget
    scale_factor = (max_budget * 0.95) / total if total > 0 else 1.0
    new_total = 0.0
    adjusted_items = []
    
    for it in items:
        orig_price = float(it.get("estimated_price", 0))
        new_price = max(100.0, round(orig_price * scale_factor, 2))
        it["estimated_price"] = new_price
        it["product_search_link"] = get_platform_search_url(
            it.get("platform", "Amazon"), 
            it.get("item_name", "item")
        )
        new_total += new_price
        adjusted_items.append(it)
    
    # If still barely over budget due to rounding or minimums, trim excess
    if new_total > max_budget:
        diff = new_total - max_budget
        if adjusted_items:
            adjusted_items[0]["estimated_price"] = max(50.0, round(adjusted_items[0]["estimated_price"] - diff - 10, 2))
            new_total = sum(it["estimated_price"] for it in adjusted_items)

    return adjusted_items, round(new_total, 2)

# ==========================================
# 1. HOME PLANNER
# ==========================================

def build_home_prompt(budget: float, room_types: List[str], items: Dict[str, int], style: str) -> str:
    rooms_str = ", ".join(room_types)
    items_str = ", ".join([f"{qty}x {name.replace('_', ' ').title()}" for name, qty in items.items() if qty > 0])
    if not items_str:
        items_str = "Standard room essentials (lighting, ceiling fans, seating, tables)"
        
    return f"""You are an expert interior designer and budget shopping assistant.
The user wants to furnish/decorate the following rooms: {rooms_str}.
Requested items/quantities: {items_str}.
Style preference: {style}.
Total maximum budget: ₹{budget:,.2f} INR (or currency equivalent).

Rules:
1. Divide and allocate the total budget across the requested rooms and items.
2. Recommend cost-effective, high-rated options from IKEA and Amazon.
3. Balance function, durability, aesthetics, and cost-effectiveness.
4. Total of all estimated_price fields MUST NOT EXCEED ₹{budget:,.2f}.
5. Return ONLY a valid JSON array of objects, with NO extra text or markdown formatting outside the JSON.

Each object must follow this exact schema:
{{
  "item_name": "Specific product name or model style",
  "category": "Furniture / Lighting / Decor / Appliance",
  "estimated_price": 4500.00,
  "platform": "IKEA" or "Amazon",
  "why_it_fits": "Brief stylish justification why this fits the style and budget"
}}
"""

def generate_home_fallback(budget: float, room_types: List[str], items: Dict[str, int], style: str) -> List[Dict[str, Any]]:
    """Generates intelligent, deterministic fallback recommendations for home interior budget."""
    rooms = room_types or ["Living Room"]
    rec_items = []
    
    # Base item catalog with platform, category, and budget percentage
    catalog = [
        {"name": f"{style} LED Warm Ceiling Chandelier", "category": "Lighting", "plat": "Amazon", "ratio": 0.08, "why": "Energy-efficient ambient illumination matching contemporary interior aesthetics."},
        {"name": "IKEA REGOLIT Pendant Lamp Shade", "category": "Lighting", "plat": "IKEA", "ratio": 0.04, "why": "Iconic minimalist paper shade offering diffused soothing light."},
        {"name": "Havells Stealth Air BLDC Ceiling Fan 1200mm", "category": "Appliance", "plat": "Amazon", "ratio": 0.12, "why": "Whisper-quiet BLDC motor with 5-star power savings and sleek aerodynamic blades."},
        {"name": "IKEA LISABO Dining Table with Solid Ash Finish", "category": "Furniture", "plat": "IKEA", "ratio": 0.22, "why": "Sturdy natural ash veneer that brings warmth and Scandinavian craftsmanship."},
        {"name": "Amazon Brand - Solimo 3-Seater Fabric Sofa Couch", "category": "Furniture", "plat": "Amazon", "ratio": 0.28, "why": "Ergonomic high-density foam cushioning with durable stain-resistant upholstery."},
        {"name": "IKEA KALLAX Shelving Unit 4x2", "category": "Storage", "plat": "IKEA", "ratio": 0.10, "why": "Versatile open storage suitable as a room divider or media unit display."},
        {"name": "Hand-Woven Natural Jute Floor Rug (5x7 ft)", "category": "Decor", "plat": "Amazon", "ratio": 0.07, "why": "Adds organic texture and defines conversation zones naturally."},
        {"name": "Blackout Linen Thermal Insulated Curtains (Set of 2)", "category": "Furnishing", "plat": "Amazon", "ratio": 0.06, "why": "Blocks glare, improves temperature regulation and gives tailored ceiling drop."}
    ]
    
    # Adjust catalog items to explicitly match user requested items if provided
    selected = []
    for item_key, qty in items.items():
        if qty <= 0:
            continue
        clean_name = item_key.replace("_", " ").title()
        plat = "IKEA" if ("table" in item_key or "chair" in item_key or "shelf" in item_key) else "Amazon"
        category = "Furniture" if ("table" in item_key or "sofa" in item_key or "bed" in item_key) else "Lighting" if "light" in item_key else "Appliance" if "fan" in item_key else "Decor"
        selected.append({
            "name": f"{qty}x {style} {clean_name}",
            "category": category,
            "plat": plat,
            "why": f"Selected to fulfill requested {qty}x count for {', '.join(rooms)} within budget."
        })
    
    # If no specific items checked, use catalog
    if not selected:
        selected = catalog[:6]

    # Allocate budget evenly/proportionally
    num = len(selected)
    share = budget / max(num, 1)
    
    for entry in selected:
        price = round(max(350.0, share * 0.92), 2)
        rec_items.append({
            "item_name": entry["name"],
            "category": entry["category"],
            "estimated_price": price,
            "platform": entry["plat"],
            "why_it_fits": entry["why"],
            "product_search_link": get_platform_search_url(entry["plat"], entry["name"])
        })
        
    final_items, _ = enforce_budget_limit(rec_items, budget)
    return final_items

def generate_home_recommendations(budget: float, room_types: List[str], items: Dict[str, int], style: str) -> Dict[str, Any]:
    client = get_gemini_client()
    summary = f"Interior budget plan for {', '.join(room_types)} in {style} style."
    recommendations = []
    
    if client and types:
        prompt = build_home_prompt(budget, room_types, items, style)
        models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        for m in models_to_try:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.3
                    )
                )
                parsed = clean_and_parse_json(response.text)
                if isinstance(parsed, dict) and "recommendations" in parsed:
                    parsed = parsed["recommendations"]
                if isinstance(parsed, list) and len(parsed) > 0:
                    recommendations = parsed
                    summary = f"Gemini AI tailored interior recommendation for {', '.join(room_types)}."
                    break
            except Exception as e:
                print(f"Gemini {m} failed for home planner: {e}")
                continue

    if not recommendations:
        recommendations = generate_home_fallback(budget, room_types, items, style)
        if not summary.endswith("(Curated Fallback)"):
            summary += " (Curated Budget Fallback)"

    final_items, total_cost = enforce_budget_limit(recommendations, budget)
    status = "Within Budget" if total_cost <= budget else "Exceeded Budget"
    
    return {
        "planner_type": "home",
        "budget": budget,
        "total_cost": total_cost,
        "budget_status": status,
        "summary": summary,
        "recommendations": final_items
    }

# ==========================================
# 2. PARTY PLANNER
# ==========================================

def build_party_prompt(budget: float, guest_count: int, event_type: str, venue_details: str, special_notes: str) -> str:
    return f"""You are a master event planner and catering budget advisor.
Plan a {event_type} event for {guest_count} guests.
Venue: {venue_details}.
Special Notes / Theme: {special_notes or 'Standard high-energy celebration'}.
Total maximum budget: ₹{budget:,.2f} INR.

Rules:
1. Divide and allocate the budget across Catering & Food, Venue Booking/Rooms, Decoration, and Entertainment.
2. Specifically recommend real services from Swiggy, Zomato, and OYO.
   - Food/Snacks/Catering: Swiggy or Zomato
   - Venue / Stay / Banquet Hall: OYO
   - Decor & Entertainment: Swiggy Instamart, Zomato or Amazon
3. Adjust menu and entertainment based on event type:
   - Birthday: Cake, fun finger foods, photo booth, balloons
   - Corporate: Professional buffet, AV equipment, premium tea/coffee
   - Wedding: Grand catering platter, floral decor, banquet suite
4. Total of all estimated_price fields MUST NOT EXCEED ₹{budget:,.2f}.
5. Return ONLY a valid JSON array of objects, NO markdown outside JSON.

Each object must follow this exact schema:
{{
  "item_name": "Specific catering platter, OYO room/hall, or decor package",
  "category": "Catering / Venue / Decoration / Entertainment",
  "estimated_price": 5000.00,
  "platform": "Swiggy" or "Zomato" or "OYO",
  "why_it_fits": "Event-specific justification for guest count and theme"
}}
"""

def generate_party_fallback(budget: float, guest_count: int, event_type: str, venue_details: str, special_notes: str) -> List[Dict[str, Any]]:
    """Intelligent fallback for party planning tailored to event type."""
    ev = event_type.lower()
    
    if "corporate" in ev:
        items = [
            {"name": f"Zomato Corporate Gourmet Box Platter ({guest_count} Pax)", "category": "Catering", "plat": "Zomato", "ratio": 0.45, "why": "Professional executive lunch boxes with wholesome balanced options."},
            {"name": "OYO Townhouse Conference & Banquet Suite", "category": "Venue", "plat": "OYO", "ratio": 0.30, "why": "Equipped with high-speed WiFi, projector facilities and breakout seating."},
            {"name": "Swiggy Artisanal Coffee & Patisserie Station", "category": "Catering", "plat": "Swiggy", "ratio": 0.15, "why": "Freshly brewed espresso and assorted pastries for networking breaks."},
            {"name": "Minimalist Corporate Backdrop & Stage Banner Kit", "category": "Decoration", "plat": "Swiggy", "ratio": 0.10, "why": "Clean branded signage and podium floral arrangement."}
        ]
    elif "wedding" in ev:
        items = [
            {"name": f"Zomato Grand Royal Feast Multi-Course Catering ({guest_count} Pax)", "category": "Catering", "plat": "Zomato", "ratio": 0.48, "why": "Extensive traditional buffet spread with welcome drinks, starters, and royal desserts."},
            {"name": "OYO Premium Banquet Hall & Family Guest Rooms", "category": "Venue", "plat": "OYO", "ratio": 0.32, "why": "Spacious ceremonial hall with air-conditioned bridal and family changing suites."},
            {"name": "Swiggy Fresh Marigold & Rose Canopy Floral Decor", "category": "Decoration", "plat": "Swiggy", "ratio": 0.12, "why": "Auspicious traditional floral entrance arch and stage mandap backdrop."},
            {"name": "Live Acoustic & Traditional Music Sound System", "category": "Entertainment", "plat": "Zomato", "ratio": 0.08, "why": "Crisp acoustic audio setup for ceremony music and vows."}
        ]
    else: # Birthday / Party
        items = [
            {"name": f"Swiggy Signature 2-Tier Celebration Cake & Desserts", "category": "Catering", "plat": "Swiggy", "ratio": 0.18, "why": "Customized themed artisanal birthday cake with mini cupcakes."},
            {"name": f"Zomato Party Starter Platters & Mocktails ({guest_count} Pax)", "category": "Catering", "plat": "Zomato", "ratio": 0.38, "why": "Crispy appetizers, pizza sliders, dips and refreshing mocktail jugs."},
            {"name": "OYO Townhouse Party Room & Lounge", "category": "Venue", "plat": "OYO", "ratio": 0.26, "why": "Vibrant celebration venue with lounge seating and ambient party lighting."},
            {"name": "Metallic Balloon Arch, Foil Curtains & LED Party Prop Kit", "category": "Decoration", "plat": "Swiggy", "ratio": 0.10, "why": "Instagrammable photo-op corner with customized age balloons."},
            {"name": "Wireless Karaoke Microphone & DJ Bass Speaker Setup", "category": "Entertainment", "plat": "Swiggy", "ratio": 0.08, "why": "Interactive high-energy entertainment for guest participation."}
        ]
        
    rec_items = []
    for entry in items:
        price = round(max(300.0, budget * entry["ratio"]), 2)
        rec_items.append({
            "item_name": entry["name"],
            "category": entry["category"],
            "estimated_price": price,
            "platform": entry["plat"],
            "why_it_fits": entry["why"],
            "product_search_link": get_platform_search_url(entry["plat"], entry["name"])
        })
        
    final_items, _ = enforce_budget_limit(rec_items, budget)
    return final_items

def generate_party_recommendations(budget: float, guest_count: int, event_type: str, venue_details: str, special_notes: str) -> Dict[str, Any]:
    client = get_gemini_client()
    summary = f"{event_type.title()} event planner for {guest_count} guests at {venue_details}."
    recommendations = []
    
    if client and types:
        prompt = build_party_prompt(budget, guest_count, event_type, venue_details, special_notes)
        models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        for m in models_to_try:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.35
                    )
                )
                parsed = clean_and_parse_json(response.text)
                if isinstance(parsed, dict) and "recommendations" in parsed:
                    parsed = parsed["recommendations"]
                if isinstance(parsed, list) and len(parsed) > 0:
                    recommendations = parsed
                    summary = f"Gemini AI customized party budget plan for {guest_count} guests."
                    break
            except Exception as e:
                print(f"Gemini {m} failed for party planner: {e}")
                continue

    if not recommendations:
        recommendations = generate_party_fallback(budget, guest_count, event_type, venue_details, special_notes)
        if not summary.endswith("(Curated Fallback)"):
            summary += " (Curated Event Fallback)"

    final_items, total_cost = enforce_budget_limit(recommendations, budget)
    status = "Within Budget" if total_cost <= budget else "Exceeded Budget"
    
    return {
        "planner_type": "party",
        "budget": budget,
        "total_cost": total_cost,
        "budget_status": status,
        "summary": summary,
        "recommendations": final_items
    }

# ==========================================
# 3. JEWELRY PLANNER (Multimodal)
# ==========================================

def build_jewelry_prompt(budget: float, occasion: str, style_preference: str, metal_preference: str, has_image: bool) -> str:
    image_instruction = ""
    if has_image:
        image_instruction = """
An outfit image is provided. Please analyze:
1. The exact color palette (primary, secondary, accent hues) of the outfit.
2. The neckline (sweetheart, V-neck, collar, boat neck, round, high neck).
3. The overall vibe and embroidery/pattern complexity.
Tailor every jewelry recommendation to complement the outfit's tones and neckline!
"""
    return f"""You are a luxury jewelry stylist and smart budget shopper.
Occasion: {occasion}.
Style Preference: {style_preference}.
Metal/Material Preference: {metal_preference}.
Total Maximum Budget: ₹{budget:,.2f} INR.
{image_instruction}
Rules:
1. Recommend matching jewelry pieces (e.g. necklace/choker, earrings/jhumkas, bracelet/bangles, rings).
2. Recommend cost-effective, high-rated options from Amazon and Flipkart.
3. Total of all estimated_price fields MUST NOT EXCEED ₹{budget:,.2f}.
4. Return ONLY a valid JSON array of objects, NO markdown outside JSON.

Each object must follow this exact schema:
{{
  "item_name": "Specific jewelry piece name (e.g., Kundan Choker Necklace Set, 925 Silver Solitaire Studs)",
  "category": "Necklace / Earrings / Bracelet / Ring / Hair Accessory",
  "estimated_price": 2500.00,
  "platform": "Amazon" or "Flipkart",
  "why_it_fits": "Styling justification explaining harmony with the occasion, style, and outfit colors"
}}
"""

def generate_jewelry_fallback(budget: float, occasion: str, style: str, metal: str, outfit_notes: str = "") -> List[Dict[str, Any]]:
    """Intelligent fallback for jewelry recommendations."""
    st = style.lower()
    occ = occasion.lower()
    
    if "traditional" in st or "wedding" in occ or "festival" in occ:
        items = [
            {"name": "Zaveri Pearls Gold-Plated Austrian Stone Kundan Choker Set with Matching Jhumkis", "category": "Necklace & Earrings", "plat": "Amazon", "ratio": 0.45, "why": "Regal heritage craftsmanship with delicate pearl drops that accentuate ethnic attire."},
            {"name": "Sukkhi 24k Micron Gold Plated Handcrafted Bangles Set of 4", "category": "Bangles", "plat": "Flipkart", "ratio": 0.25, "why": "Intricate filigree work designed to stack elegantly with traditional wristwear."},
            {"name": "Shining Diva Fashion Adjustable Kundan Statement Finger Ring", "category": "Ring", "plat": "Amazon", "ratio": 0.15, "why": "Center floral cluster ring that catches light during ceremonial rituals."},
            {"name": "Traditional Gold Plated Pearl Maang Tikka", "category": "Hair Accessory", "plat": "Flipkart", "ratio": 0.15, "why": "Frames the face delicately without clashing with the choker neckline."}
        ]
    elif "minimalist" in st or "casual" in occ or "office" in occ:
        items = [
            {"name": "GIVA 925 Sterling Silver Zircon Solitaire Pendant with Chain", "category": "Necklace", "plat": "Amazon", "ratio": 0.40, "why": "Understated brilliance that complements sharp collars and casual shirts."},
            {"name": "Yellow Chimes Silver Plated Classic Stud Earrings", "category": "Earrings", "plat": "Flipkart", "ratio": 0.25, "why": "Timeless cubic zirconia studs suitable for all-day office comfort."},
            {"name": "Clara 925 Sterling Silver Minimalist Adjustable Tennis Bracelet", "category": "Bracelet", "plat": "Amazon", "ratio": 0.22, "why": "Sleek shimmering band adding understated polish to the wrist."},
            {"name": "Sleek Silver Thin Band Ring with Micro Pave Stone", "category": "Ring", "plat": "Flipkart", "ratio": 0.13, "why": "Subtle, featherlight ring ideal for effortless everyday elegance."}
        ]
    else: # Contemporary / Party
        items = [
            {"name": "YouBella Contemporary Rose Gold Plated Crystal Collar Necklace", "category": "Necklace", "plat": "Amazon", "ratio": 0.42, "why": "Gleaming rose-gold tones that flatter evening party gowns and cocktail silhouettes."},
            {"name": "Voylla Dazzling Crystal Chandelier Drop Dangler Earrings", "category": "Earrings", "plat": "Flipkart", "ratio": 0.28, "why": "Cascading crystal drops that shimmer under dramatic party lighting."},
            {"name": "Swarovski Element Crystal Open Cuff Bracelet", "category": "Bracelet", "plat": "Amazon", "ratio": 0.18, "why": "Modern geometric cuff with secure clasp and dazzling gemstone accents."},
            {"name": "Multi-Layered Stackable Cocktail Statement Rings", "category": "Ring", "plat": "Flipkart", "ratio": 0.12, "why": "Trendy layered ring set allowing versatile mix-and-match styling."}
        ]

    rec_items = []
    for entry in items:
        price = round(max(250.0, budget * entry["ratio"]), 2)
        rec_items.append({
            "item_name": entry["name"],
            "category": entry["category"],
            "estimated_price": price,
            "platform": entry["plat"],
            "why_it_fits": entry["why"],
            "product_search_link": get_platform_search_url(entry["plat"], entry["name"])
        })
        
    final_items, _ = enforce_budget_limit(rec_items, budget)
    return final_items

def generate_jewelry_recommendations(
    budget: float, 
    occasion: str, 
    style_preference: str, 
    metal_preference: str = "Any", 
    image_bytes: Optional[bytes] = None, 
    mime_type: Optional[str] = None
) -> Dict[str, Any]:
    client = get_gemini_client()
    summary = f"Jewelry pairing for {occasion} in {style_preference} style."
    recommendations = []
    
    if client and types:
        prompt = build_jewelry_prompt(budget, occasion, style_preference, metal_preference, has_image=bool(image_bytes))
        
        contents = []
        if image_bytes and mime_type:
            try:
                contents.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
            except Exception as e:
                print(f"Error preparing image part for Gemini: {e}")
        contents.append(prompt)
        
        models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        for m in models_to_try:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.35
                    )
                )
                parsed = clean_and_parse_json(response.text)
                if isinstance(parsed, dict) and "recommendations" in parsed:
                    parsed = parsed["recommendations"]
                if isinstance(parsed, list) and len(parsed) > 0:
                    recommendations = parsed
                    img_note = " with Multimodal Outfit Color Matching" if image_bytes else ""
                    summary = f"Gemini AI tailored jewelry recommendation for {occasion}{img_note}."
                    break
            except Exception as e:
                print(f"Gemini {m} failed for jewelry planner: {e}")
                continue

    if not recommendations:
        recommendations = generate_jewelry_fallback(budget, occasion, style_preference, metal_preference)
        if not summary.endswith("(Curated Fallback)"):
            summary += " (Curated Stylist Fallback)"

    final_items, total_cost = enforce_budget_limit(recommendations, budget)
    status = "Within Budget" if total_cost <= budget else "Exceeded Budget"
    
    return {
        "planner_type": "jewelry",
        "budget": budget,
        "total_cost": total_cost,
        "budget_status": status,
        "summary": summary,
        "recommendations": final_items
    }
