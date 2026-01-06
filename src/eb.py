import base64
import json
import logging
import os
import dotenv
from datetime import datetime
from pathlib import Path

import requests

# Configure logging to file only
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs.log', encoding='utf-8', mode='a')
    ]
)
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
    logger.info("Starting OAuth token request")
    credentials = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    logger.debug("Credentials encoded successfully")

    try:
        logger.debug(f"Sending OAuth request to {OAUTH_URL}")
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
        logger.debug(f"OAuth response status code: {response.status_code}")
    except requests.Timeout:
        logger.error("OAuth authentication timed out")
        raise EbayAuthError("Authentication timed out")
    except requests.RequestException as e:
        logger.error(f"OAuth request exception: {e}")
        raise EbayAuthError(f"Authentication request failed: {e}")

    if response.status_code == 401:
        logger.error("OAuth authentication failed: Invalid credentials")
        raise EbayAuthError("Invalid credentials")
    if response.status_code != 200:
        logger.error(f"OAuth authentication failed with status code {response.status_code}")
        raise EbayAuthError(f"Auth failed (HTTP {response.status_code})")

    token = response.json()["access_token"]
    logger.info("OAuth token acquired successfully")
    return token


def load_last_seen() -> dict | None:
    logger.debug(f"Loading last seen data from {TRACKER_FILE}")
    if not TRACKER_FILE.exists():
        logger.info("Tracker file does not exist, returning None")
        return None
    try:
        with open(TRACKER_FILE, "r") as f:
            data = json.load(f)
            logger.info(f"Loaded last seen item: {data.get('item_id', 'Unknown')}")
            return data
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load tracker file: {e}")
        return None


def save_last_seen(item: dict) -> None:
    item_id = item.get("itemId")
    logger.debug(f"Saving last seen item: {item_id}")
    try:
        data = {
            "item_id": item_id,
            "item_creation_date": item.get("itemCreationDate"),
            "title": item.get("title"),
            "saved_at": datetime.now().isoformat()
        }
        with open(TRACKER_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Successfully saved last seen item: {item_id}")
    except IOError as e:
        logger.error(f"Failed to save tracker file: {e}")


def parse_ebay_date(date_str: str) -> datetime:
    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))


def filter_new_listings(items: list, last_seen: dict | None) -> list:
    logger.debug(f"Filtering new listings from {len(items)} total items")
    if not last_seen:
        logger.info("No last seen data, returning all items")
        return items

    try:
        last_seen_date = parse_ebay_date(last_seen["item_creation_date"])
        last_seen_id = last_seen["item_id"]
        logger.debug(f"Last seen: ID={last_seen_id}, Date={last_seen_date}")
    except (KeyError, ValueError) as e:
        logger.warning(f"Invalid tracker data, returning all items: {e}")
        return items

    new_items = []
    for item in items:
        try:
            item_date = parse_ebay_date(item.get("itemCreationDate", ""))
            item_id = item.get("itemId")

            if item_id == last_seen_id:
                logger.debug(f"Reached last seen item: {item_id}")
                break
            if item_date > last_seen_date:
                new_items.append(item)
                logger.debug(f"New item found: {item_id} - {item.get('title', 'No title')[:50]}")
            else:
                logger.debug(f"Item {item_id} is older than last seen, stopping filter")
                break
        except ValueError:
            logger.warning(f"Skipping item with invalid date: {item.get('itemId')}")
            continue

    logger.info(f"Filtered {len(new_items)} new listings")
    return new_items


def search_ebay(access_token: str, marketplace: str = "EBAY_GB", limit: int = 50) -> list:
    logger.info(f"Searching eBay: marketplace={marketplace}, limit={limit}")
    try:
        logger.debug(f"Sending search request to {BROWSE_API_URL}")
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
        logger.debug(f"Search response status code: {response.status_code}")
    except requests.Timeout:
        logger.error("eBay search request timed out")
        raise EbayAPIError("Search request timed out")
    except requests.RequestException as e:
        logger.error(f"eBay search request exception: {e}")
        raise EbayAPIError(f"Search request failed: {e}")

    if response.status_code == 401:
        logger.error("eBay search failed: Token expired or invalid")
        raise EbayAuthError("Token expired or invalid")
    if response.status_code != 200:
        logger.error(f"eBay search failed with status code {response.status_code}")
        raise EbayAPIError(f"Search failed (HTTP {response.status_code})")

    items = response.json().get("itemSummaries", [])
    logger.info(f"Search returned {len(items)} items")
    return items


def format_listing(item: dict) -> dict:
    item_id = item.get("itemId")
    logger.debug(f"Formatting listing: {item_id}")

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
        logger.debug(f"Delivery info: {delivery}")

    formatted = {
        "title": item.get("title", "No title"),
        "price": f"{price.get('currency', '')} {price.get('value', '')}".strip() or "Unknown",
        "image": item.get("image", {}).get("imageUrl"),
        "url": item.get("itemWebUrl"),
        "delivery": delivery
    }
    logger.debug(f"Formatted listing: {formatted['title']} - {formatted['price']}")
    return formatted


def get_new_listings(marketplace: str = "EBAY_GB") -> list[dict]:
    """
    Fetch new eBay listings.

    Returns:
        list[dict]: List of new listings

    Raises:
        EbayAuthError: Authentication issues
        EbayAPIError: API request issues
    """
    logger.info(f"Starting get_new_listings for marketplace: {marketplace}")

    token = get_oauth_token()
    last_seen = load_last_seen()

    all_items = search_ebay(token, marketplace)
    if not all_items:
        logger.info("No items returned from search")
        return []

    new_items = filter_new_listings(all_items, last_seen)
    save_last_seen(all_items[0])

    formatted_listings = [format_listing(item) for item in new_items]
    logger.info(f"Returning {len(formatted_listings)} new listings")
    return formatted_listings
