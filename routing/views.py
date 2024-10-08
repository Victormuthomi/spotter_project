import csv
import os
import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from geopy.geocoders import Nominatim

# GraphHopper API key for route calculations
GRAPH_HOPPER_API_KEY = '05ebbe6b-7254-41e1-8333-bed7c496edc1'

# Path to your CSV file containing fuel prices
CSV_FILE_PATH = os.path.join(settings.BASE_DIR, 'routing', 'fuel_data', 'fuel-prices-for-be-assessment.csv')

def load_fuel_prices():
    fuel_data = {}
    try:
        with open(CSV_FILE_PATH, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                city = row.get('City')
                retail_price = row.get('Retail Price')

                if city and retail_price:
                    fuel_data[city] = float(retail_price)
                else:
                    print(f"Missing data in row: {row}")
    except FileNotFoundError:
        raise Exception(f"CSV file not found at path: {CSV_FILE_PATH}")
    return fuel_data

# Load the fuel prices from the CSV file at the module level
fuel_prices = load_fuel_prices()

@require_GET
def calculate_route(request):
    # Get start and finish locations from the request
    start = request.GET.get('start')
    finish = request.GET.get('finish')

    # Check if start and finish are provided
    if not start or not finish:
        return JsonResponse({'error': 'Start and finish locations are required'}, status=400)

    try:
        # Initialize Nominatim geocoder
        geolocator = Nominatim(user_agent="fuel_optimizer")

        # Get coordinates for start and finish locations
        start_location = geolocator.geocode(start)
        finish_location = geolocator.geocode(finish)

        # Check if geocoding was successful
        if not start_location or not finish_location:
            return JsonResponse({'error': 'Invalid start or finish locations'}, status=400)

        # Prepare coordinates in the required format
        start_coords = f"{start_location.latitude},{start_location.longitude}"
        finish_coords = f"{finish_location.latitude},{finish_location.longitude}"

        # Prepare the request to the GraphHopper API
        graphhopper_url = 'https://graphhopper.com/api/1/route'
        params = {
            'point': [start_coords, finish_coords],
            'vehicle': 'car',
            'key': GRAPH_HOPPER_API_KEY,
        }

        # Make the API request
        response = requests.get(graphhopper_url, params=params)
        response_data = response.json()

        # Check the API response status
        if response.status_code != 200:
            return JsonResponse({'error': 'Failed to retrieve data from the GraphHopper API.'}, status=500)

        # Extracting route data
        route_data = response_data.get('paths', [])[0]
        instructions = route_data.get('instructions', [])

        # Total distance and time
        total_distance_km = route_data['distance'] / 1000  # Convert meters to kilometers
        total_time_sec = route_data['time'] / 1000  # Convert milliseconds to seconds

        # Calculate total distance in miles
        total_distance_miles = total_distance_km / 1.60934

        # Check if the distance exceeds 500 miles
        if total_distance_miles > 500:
            return JsonResponse({'error': 'The route exceeds the maximum allowed distance of 500 miles.'}, status=400)

        # Calculate fuel used
        fuel_efficiency_mpg = 10  # 10 miles per gallon
        total_fuel_used_gallons = total_distance_miles / fuel_efficiency_mpg

        # Create a list to hold fuel price information at the fuel stations
        fuel_stations = []
        total_fuel_cost = 0

        # Calculate fuel costs and collect fuel station information
        for instruction in instructions:
            # Assuming that each instruction provides some way to derive a location
            city_name = instruction.get('street_name', 'Unknown')
            cost_per_gallon = fuel_prices.get(city_name, None)

            if cost_per_gallon is not None:
                fuel_stations.append({
                    'city': city_name,
                    'cost_per_gallon': cost_per_gallon,
                })
                total_fuel_cost += total_fuel_used_gallons * cost_per_gallon

        # Create the final response
        response_data = {
            'total_distance_km': total_distance_km,
            'total_time_sec': total_time_sec,
            'total_fuel_used_gallons': total_fuel_used_gallons,
            'total_fuel_cost': total_fuel_cost,
            'instructions': [
                {
                    'text': instruction.get('text'),
                    'distance': instruction.get('distance'),
                    'time': instruction.get('time'),
                    'street_name': instruction.get('street_name', 'Unknown'),
                }
                for instruction in instructions
            ],
            'fuel_stations': fuel_stations,
        }

        return JsonResponse(response_data)

    except Exception as e:
        # Handle any unexpected errors
        return JsonResponse({'error': str(e)}, status=500)
