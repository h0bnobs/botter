import base64
import json
import logging
import os
import dotenv
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

dotenv.load_dotenv()
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")

TRACKER_FILE = Path(__file__).parent / "ebay_last_seen.json"
OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


class EbayError(Exception):
    """Base exception for eBay API errors"""
    pass


class EbayAuthError(EbayError):
    """Authentication failed"""
    pass


class EbayAPIError(EbayError):
    """API request failed"""
    pass


def get_oauth_token() -> str:
    credentials = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    try:
        response = requests.post(
            OAUTH_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}"
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope"
            },
            timeout=10
        )
    except requests.Timeout:
        raise EbayAuthError("Authentication timed out")
    except requests.RequestException as e:
        raise EbayAuthError(f"Authentication request failed: {e}")

    if response.status_code == 401:
        raise EbayAuthError("Invalid credentials")
    if response.status_code != 200:
        raise EbayAuthError(f"Auth failed (HTTP {response.status_code})")

    return response.json()["access_token"]


def load_last_seen() -> dict | None:
    if not TRACKER_FILE.exists():
        return None
    try:
        with open(TRACKER_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load tracker file: {e}")
        return None


def save_last_seen(item: dict) -> None:
    try:
        with open(TRACKER_FILE, "w") as f:
            json.dump({
                "item_id": item.get("itemId"),
                "item_creation_date": item.get("itemCreationDate"),
                "title": item.get("title"),
                "saved_at": datetime.now().isoformat()
            }, f, indent=2)
    except IOError as e:
        logger.error(f"Failed to save tracker file: {e}")


def parse_ebay_date(date_str: str) -> datetime:
    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))


def filter_new_listings(items: list, last_seen: dict | None) -> list:
    if not last_seen:
        return items

    try:
        last_seen_date = parse_ebay_date(last_seen["item_creation_date"])
        last_seen_id = last_seen["item_id"]
    except (KeyError, ValueError) as e:
        logger.warning(f"Invalid tracker data, returning all items: {e}")
        return items

    new_items = []
    for item in items:
        try:
            item_date = parse_ebay_date(item.get("itemCreationDate", ""))
            item_id = item.get("itemId")

            if item_id == last_seen_id:
                break
            if item_date > last_seen_date:
                new_items.append(item)
            else:
                break
        except ValueError:
            continue

    return new_items


def search_ebay(access_token: str, marketplace: str = "EBAY_GB", limit: int = 50) -> list:
    try:
        response = requests.get(
            BROWSE_API_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-EBAY-C-MARKETPLACE-ID": marketplace,
                "Content-Type": "application/json"
            },
            params={
                "category_ids": "179",
                "filter": "conditionIds:{7000}",
                "sort": "newlyListed",
                "limit": limit
            },
            timeout=15
        )
    except requests.Timeout:
        raise EbayAPIError("Search request timed out")
    except requests.RequestException as e:
        raise EbayAPIError(f"Search request failed: {e}")

    if response.status_code == 401:
        raise EbayAuthError("Token expired or invalid")
    if response.status_code != 200:
        raise EbayAPIError(f"Search failed (HTTP {response.status_code})")

    return response.json().get("itemSummaries", [])


def format_listing(item: dict) -> dict:
    price = item.get("price", {})
    shipping = item.get("shippingOptions", [])

    delivery = None
    if shipping:
        ship_cost = shipping[0].get("shippingCost", {})
        delivery = {
            "cost": f"{ship_cost.get('currency', '')} {ship_cost.get('value', '')}".strip() or "Unknown",
            "min_date": shipping[0].get("minEstimatedDeliveryDate", "").split("T")[0] or None,
            "max_date": shipping[0].get("maxEstimatedDeliveryDate", "").split("T")[0] or None
        }

    return {
        "title": item.get("title", "No title"),
        "price": f"{price.get('currency', '')} {price.get('value', '')}".strip() or "Unknown",
        "image": item.get("image", {}).get("imageUrl"),
        "url": item.get("itemWebUrl"),
        "delivery": delivery
    }


def get_new_listings(marketplace: str = "EBAY_GB") -> list[dict]:
    """
    Fetch new eBay listings.

    Returns:
        list[dict]: List of new listings

    Raises:
        EbayAuthError: Authentication issues
        EbayAPIError: API request issues
    """
    token = get_oauth_token()
    last_seen = load_last_seen()

    all_items = search_ebay(token, marketplace)
    if not all_items:
        return []

    new_items = filter_new_listings(all_items, last_seen)
    save_last_seen(all_items[0])

    return [format_listing(item) for item in new_items]
