import logging
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-01-22aa206edd68"
COLLECTION_NAME = "destinations"

SEED_DESTINATIONS = [
    {
        "id": "kyoto-japan",
        "name": "Kyoto, Japan",
        "category": "Culture & History",
        "location": "Kansai Region, Japan",
        "price_range": "$$",
        "rating": 4.9,
        "description": "Famous for its classical Buddhist temples, gardens, imperial palaces, Shinto shrines, and traditional wooden houses.",
        "highlights": ["Fushimi Inari Shrine", "Arashiyama Bamboo Grove", "Gion Geisha District"],
        "best_season": "Spring (Cherry Blossoms) & Autumn"
    },
    {
        "id": "santorini-greece",
        "name": "Santorini, Greece",
        "category": "Beach & Relaxation",
        "location": "Cyclades, Aegean Sea",
        "price_range": "$$$",
        "rating": 4.8,
        "description": "Stunning volcanic island known for whitewashed cubiform houses in Oia and Fira, dramatic cliffside views, and romantic sunsets.",
        "highlights": ["Oia Sunset Viewpoint", "Red Beach", "Ancient Akrotiri"],
        "best_season": "May to October"
    },
    {
        "id": "banff-canada",
        "name": "Banff National Park, Canada",
        "category": "Nature & Adventure",
        "location": "Alberta, Rocky Mountains",
        "price_range": "$$",
        "rating": 4.9,
        "description": "Canada's oldest national park featuring turquoise glacial lakes, majestic mountain peaks, and abundant wildlife.",
        "highlights": ["Lake Louise", "Moraine Lake", "Banff Upper Hot Springs"],
        "best_season": "June to September (Hiking) & Winter (Skiing)"
    },
    {
        "id": "reykjavik-iceland",
        "name": "Reykjavik & Golden Circle, Iceland",
        "category": "Northern Lights & Geothermal",
        "location": "Capital Region, Iceland",
        "price_range": "$$$",
        "rating": 4.7,
        "description": "Gateway to Iceland's dramatic volcanic landscapes, hot springs, waterfalls, geysers, and mesmerising Northern Lights.",
        "highlights": ["Blue Lagoon", "Gullfoss Waterfall", "Thingvellir National Park"],
        "best_season": "September to April (Aurora) / Summer (Midnight Sun)"
    },
    {
        "id": "cusco-peru",
        "name": "Cusco & Machu Picchu, Peru",
        "category": "Culture & History",
        "location": "Peruvian Andes",
        "price_range": "$$",
        "rating": 4.9,
        "description": "Ancient capital of the Inca Empire situated high in the Andes, serving as the gateway to the legendary citadel of Machu Picchu.",
        "highlights": ["Machu Picchu Citadel", "Sacred Valley", "Sacsayhuamán Complex"],
        "best_season": "May to October (Dry Season)"
    }
]


def seed_database():
    import google.auth
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    db = firestore.Client(project=PROJECT_ID, credentials=credentials)
    print(f"Connecting to Firestore in project: '{PROJECT_ID}'...")
    
    collection_ref = db.collection(COLLECTION_NAME)
    for dest in SEED_DESTINATIONS:
        doc_ref = collection_ref.document(dest["id"])
        doc_ref.set(dest)
        print(f"  Seeded destination: {dest['name']} ({dest['id']})")
        
    print(f"✅ Successfully seeded {len(SEED_DESTINATIONS)} destinations into Firestore collection '{COLLECTION_NAME}'!")

if __name__ == "__main__":
    seed_database()
