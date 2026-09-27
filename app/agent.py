# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from app.a2ui_utils import a2ui_callback

load_dotenv()

MODEL = "gemini-2.5-flash"
PROJECT_ID = "qwiklabs-gcp-01-22aa206edd68"
LOCATION = "us-east1"
BUCKET_NAME = "travel-concierge-media-qwiklabs-gcp-01-22aa206edd68"
COLLECTION_NAME = "destinations"
MEMORY_BANK_ID = "3523633500836069376"

DEPLOYMENT_METADATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "deployment_metadata.json"
)


def get_code_executor() -> AgentEngineSandboxCodeExecutor:
    """Configures AgentEngineSandboxCodeExecutor using deployment_metadata.json if available."""
    sandbox_name = None
    agent_engine_name = None

    if os.path.exists(DEPLOYMENT_METADATA_FILE):
        try:
            with open(DEPLOYMENT_METADATA_FILE, "r") as f:
                metadata = json.load(f)
                sandbox_name = metadata.get("sandbox_resource_name")
                agent_engine_name = metadata.get("remote_agent_runtime_id")
        except Exception:
            pass

    if sandbox_name:
        return AgentEngineSandboxCodeExecutor(sandbox_resource_name=sandbox_name)
    elif agent_engine_name:
        return AgentEngineSandboxCodeExecutor(agent_engine_resource_name=agent_engine_name)
    else:
        return AgentEngineSandboxCodeExecutor(
            agent_engine_resource_name=f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{MEMORY_BANK_ID}"
        )


def get_memory_service() -> VertexAiMemoryBankService:
    """Returns a VertexAiMemoryBankService pointing to the Agent Engine memory bank."""
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location=LOCATION,
        agent_engine_id=MEMORY_BANK_ID,
    )


async def generate_memories_callback(callback_context: CallbackContext) -> None:
    """Extracts durable facts and preferences from the session and saves them to Memory Bank."""
    await callback_context.add_session_to_memory()
    return None


def get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with the hardcoded GCP project ID."""
    return firestore.Client(project=PROJECT_ID)


def search_destinations(category: Optional[str] = None) -> list[dict[str, Any]]:
    """Searches and lists travel destinations stored in the Firestore travel catalog.

    Args:
        category: Optional category filter (e.g. 'Culture & History', 'Beach & Relaxation', 'Nature & Adventure').

    Returns:
        A list of destination dictionaries matching the query.
    """
    db = get_firestore_client()
    query_ref = db.collection(COLLECTION_NAME)
    
    if category:
        query_ref = query_ref.where("category", "==", category)
        
    docs = query_ref.stream()
    results = [doc.to_dict() for doc in docs]
    return results


def get_destination_details(destination_id: str) -> dict[str, Any]:
    """Fetches detailed information for a specific travel destination by ID.

    Args:
        destination_id: The unique identifier of the destination (e.g. 'kyoto-japan', 'santorini-greece').

    Returns:
        A dictionary containing the destination details or an error dictionary if not found.
    """
    db = get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(destination_id)
    doc = doc_ref.get()
    
    if doc.exists:
        return doc.to_dict()
    return {"error": f"Destination with ID '{destination_id}' not found."}


def add_destination(
    destination_id: str,
    name: str,
    category: str,
    location: str,
    price_range: str,
    rating: float,
    description: str,
    highlights: list[str],
    best_season: str,
) -> dict[str, Any]:
    """Adds or updates a travel destination in the Firestore catalog.

    Args:
        destination_id: Unique slug/ID for the destination (e.g. 'tokyo-japan').
        name: Name of the destination.
        category: Category (e.g., 'Culture & History', 'Beach & Relaxation', 'Nature & Adventure').
        location: Geographical region or country.
        price_range: Price indicator ('$', '$$', '$$$').
        rating: Rating out of 5.0 (e.g. 4.8).
        description: Brief summary of the destination.
        highlights: Key attractions or activities list.
        best_season: Ideal time to visit.

    Returns:
        A confirmation dictionary with the saved destination details.
    """
    db = get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(destination_id)
    
    data = {
        "id": destination_id,
        "name": name,
        "category": category,
        "location": location,
        "price_range": price_range,
        "rating": rating,
        "description": description,
        "highlights": highlights,
        "best_season": best_season,
    }
    
    doc_ref.set(data)
    return {"status": "success", "message": f"Added destination '{name}' to Firestore catalog.", "data": data}


def geocode_address(address: str) -> dict[str, Any]:
    """Uses the Google Maps Geocoding API to convert a street address, place name, or landmark into coordinates.

    Args:
        address: Address, location, or landmark name to geocode (e.g. 'Kyoto Station', 'Eiffel Tower').

    Returns:
        A dictionary containing name, formatted address, and latitude/longitude coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY is not configured in environment."}

    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        res = httpx.get(url, params={"address": address, "key": api_key}, timeout=10.0).json()
        results = res.get("results")
        if not results:
            return {"error": f"No geocoding results found for address: {address}"}

        first = results[0]
        location = first.get("geometry", {}).get("location", {})
        return {
            "name": address,
            "address": first.get("formatted_address"),
            "location": {
                "latitude": location.get("lat"),
                "longitude": location.get("lng"),
            },
        }
    except Exception as e:
        return {"error": f"Geocoding request failed: {str(e)}"}


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "restaurant",
    radius_meters: float = 1000.0,
) -> list[dict[str, Any]]:
    """Uses the Google Maps Places API (New) to search for nearby places of a given type around a coordinate.

    Args:
        latitude: Latitude of the center location (e.g. 35.02107).
        longitude: Longitude of the center location (e.g. 135.75385).
        place_type: Place type to filter for (e.g. 'restaurant', 'cafe', 'tourist_attraction', 'museum', 'lodging').
        radius_meters: Search radius in meters (default 1000.0 meters).

    Returns:
        A list of nearby places with name, formatted address, and latitude/longitude coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return [{"error": "GOOGLE_MAPS_API_KEY is not configured in environment."}]

    try:
        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
        }
        payload = {
            "includedTypes": [place_type],
            "maxResultCount": 5,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": float(radius_meters),
                }
            },
        }

        res = httpx.post(url, headers=headers, json=payload, timeout=10.0).json()
        places = res.get("places", [])

        results = []
        for p in places:
            results.append({
                "name": p.get("displayName", {}).get("text", "Unknown"),
                "address": p.get("formattedAddress", "No address available"),
                "location": p.get("location", {}),
            })
        return results
    except Exception as e:
        return [{"error": f"Places API search failed: {str(e)}"}]


def get_live_weather(location: str) -> dict[str, Any]:
    """Fetches real-time live weather conditions for any city or destination worldwide using the Open-Meteo API.

    Args:
        location: City or destination name (e.g. 'Kyoto', 'Santorini', 'Tokyo').

    Returns:
        A dictionary containing location details, current temperature in °C and °F, and wind speed.
    """
    try:
        geo_res = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "en", "format": "json"},
            timeout=10.0,
        ).json()

        results = geo_res.get("results")
        if not results:
            return {"error": f"Could not find coordinates for location: {location}"}

        place = results[0]
        lat, lon = place["latitude"], place["longitude"]
        name = place.get("name", location)
        country = place.get("country", "")

        weather_res = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "current_weather": True},
            timeout=10.0,
        ).json()

        cw = weather_res.get("current_weather", {})
        temp_c = cw.get("temperature")
        temp_f = round((temp_c * 9 / 5) + 32, 1) if temp_c is not None else None

        return {
            "location": f"{name}, {country}".strip(", "),
            "temperature_celsius": temp_c,
            "temperature_fahrenheit": temp_f,
            "windspeed_kmh": cw.get("windspeed"),
            "is_daytime": bool(cw.get("is_day")),
        }
    except Exception as e:
        return {"error": f"Failed to fetch live weather for '{location}': {str(e)}"}


def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict[str, Any]:
    """Converts a monetary amount between world currencies using live foreign exchange rates.

    Args:
        amount: The monetary value to convert (e.g. 100.0).
        from_currency: 3-letter source currency code (e.g. 'USD', 'EUR', 'GBP').
        to_currency: 3-letter target currency code (e.g. 'JPY', 'EUR', 'CAD').

    Returns:
        A dictionary containing the real-time exchange rate and converted amount.
    """
    try:
        api_key = os.environ.get("EXCHANGE_RATE_API_KEY")
        base = from_currency.upper().strip()
        target = to_currency.upper().strip()

        if api_key:
            url = f"https://v6.exchangerate-api.com/v6/{api_key}/pair/{base}/{target}/{amount}"
            res = httpx.get(url, timeout=10.0).json()
            if res.get("result") == "success":
                return {
                    "original_amount": amount,
                    "from_currency": base,
                    "to_currency": target,
                    "exchange_rate": res.get("conversion_rate"),
                    "converted_amount": res.get("conversion_result"),
                }

        # Public open exchange rate endpoint
        url = f"https://api.exchangerate-api.com/v4/latest/{base}"
        res = httpx.get(url, timeout=10.0).json()
        rates = res.get("rates", {})

        if target not in rates:
            return {"error": f"Currency code '{target}' not supported."}

        rate = rates[target]
        converted = round(amount * rate, 2)
        return {
            "original_amount": amount,
            "from_currency": base,
            "to_currency": target,
            "exchange_rate": rate,
            "converted_amount": converted,
        }
    except Exception as e:
        return {"error": f"Failed to fetch currency conversion rates: {str(e)}"}


async def generate_destination_image(
    prompt: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Generates an image for a travel destination or attraction using Gemini (gemini-3.1-flash-lite-image) in the global region,
    saves the image as an artifact, uploads the image bytes directly to public Cloud Storage, and returns the public HTTPS URL.

    Args:
        prompt: Description of the travel image to generate (e.g. 'Golden Pavilion in Kyoto during autumn').
        tool_context: Context for saving artifacts in the agent playground.

    Returns:
        A dictionary containing the public image URL, bucket name, object key, and status.
    """
    try:
        genai_client = genai.Client(
            vertexai=True,
            project=PROJECT_ID,
            location="global",
        )

        res = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=f"High quality travel photo: {prompt}",
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )

        parts = res.candidates[0].content.parts
        img_bytes = None
        mime_type = "image/jpeg"

        for p in parts:
            if p.inline_data:
                img_bytes = p.inline_data.data
                if p.inline_data.mime_type:
                    mime_type = p.inline_data.mime_type
                break

        if not img_bytes:
            return {"error": "Failed to extract image bytes from model response."}

        safe_slug = "".join(c if c.isalnum() else "_" for c in prompt[:30]).strip("_").lower()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"destination_{safe_slug}_{timestamp}.jpg"

        # 1. Save with tool_context.save_artifact
        artifact_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload image bytes directly to public GCS bucket
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(img_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "message": f"Successfully generated travel image for '{prompt}'",
            "public_url": public_url,
            "filename": filename,
            "bucket": BUCKET_NAME,
        }
    except Exception as e:
        return {"error": f"Image generation failed: {str(e)}"}


async def generate_destination_video(
    prompt: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Generates a short preview video for a travel destination or attraction using Google's Omni model (gemini-omni-flash-preview) in the global region,
    saves the video as an artifact, uploads the video bytes directly to public Cloud Storage, and returns the public HTTPS URL.

    Args:
        prompt: Description of the travel video to generate (e.g. 'Short video of sunset over Kyoto bamboo forest').
        tool_context: Context for saving artifacts in the agent playground.

    Returns:
        A dictionary containing the public video URL, bucket name, filename, and status.
    """
    try:
        genai_client = genai.Client(
            vertexai=True,
            project=PROJECT_ID,
            location="global",
        )

        interaction = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=[{"type": "text", "text": f"Short travel video preview: {prompt}"}],
            response_format=[
                {
                    "type": "video",
                    "aspect_ratio": "16:9",
                    "duration": "3s",
                }
            ],
        )

        video_bytes = None
        mime_type = "video/mp4"

        interaction_dict = interaction.model_dump() if hasattr(interaction, "model_dump") else {}
        for step in interaction_dict.get("steps", []):
            if step.get("type") == "model_output":
                for item in step.get("content", []):
                    if item.get("type") == "video" or "video" in item.get("mime_type", ""):
                        raw_b64 = item.get("data")
                        if raw_b64:
                            video_bytes = base64.b64decode(raw_b64)
                            if item.get("mime_type"):
                                mime_type = item.get("mime_type")
                            break

        if not video_bytes:
            return {"error": "Failed to extract video bytes from gemini-omni-flash-preview response."}

        safe_slug = "".join(c if c.isalnum() else "_" for c in prompt[:30]).strip("_").lower()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"video_{safe_slug}_{timestamp}.mp4"

        # 1. Save with tool_context.save_artifact so it shows up in Playground's Artifacts panel
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload video bytes directly to public GCS bucket
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "message": f"Successfully generated travel video preview for '{prompt}'",
            "public_url": public_url,
            "filename": filename,
            "bucket": BUCKET_NAME,
        }
    except Exception as e:
        return {"error": f"Video generation failed: {str(e)}"}



def get_current_time(query: str) -> str:
    """Gets the current time for a destination city.

    Args:
        query: Name of the city or location.

    Returns:
        Formatted local time.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    elif "kyoto" in query.lower() or "japan" in query.lower():
        tz_identifier = "Asia/Tokyo"
    else:
        tz_identifier = "UTC"

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are an expert travel concierge assistant helping users discover travel destinations, "
        "plan itineraries, calculate travel budgets, look up coordinates with geocode_address, "
        "find nearby attractions with find_nearby_places, generate travel images, and run Python code for travel math calculations."
    ),
    workflow_description=(
        "Analyze the request and return structured UI when appropriate. "
        "You MUST remember and respect all user allergies, dietary restrictions (e.g. peanuts, shellfish, gluten, dairy), health requirements, and stated preferences from previous conversations. "
        "Always check preloaded user memories for allergies and tailor all food, dining, itinerary, and activity recommendations to strictly avoid any identified user allergens. "
        "When executing Python code, write the code inside a ```python ... ``` block. "
        "DO NOT attempt to call a function tool named 'google:python_interpreter'. "
        "Use search_destinations, get_destination_details, and add_destination to interact with Firestore, "
        "use get_live_weather for live weather, and convert_currency for live exchange rates."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    # Keep in sync with agents-cli-manifest.yaml
    name="travel_concierge",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    code_executor=get_code_executor(),
    tools=[
        search_destinations,
        get_destination_details,
        add_destination,
        geocode_address,
        find_nearby_places,
        get_live_weather,
        convert_currency,
        generate_destination_image,
        generate_destination_video,
        get_current_time,
        PreloadMemoryTool(),
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
