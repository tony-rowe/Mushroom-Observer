import argparse
import time
import pandas as pd
import requests
import folium
from folium.plugins import HeatMap
import os
import json
import logging
from logging.handlers import RotatingFileHandler
import datetime
import sys
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich import print as rprint

# Constants
CACHE_TIMEOUT = 43200
MUSHROOM_FILE = 'mushrooms.txt'
DATA_DIR = 'mushroom_data'
API_RATE_LIMIT = 0.5  # seconds between requests
API_BASE_URL = 'https://api.inaturalist.org/v1'
PLACE_IDS = [10]  # Oregon
DEFAULT_MAP_CENTER = [44.1, -120.5]  # Oregon/Washington center
REPORTS_DIR = 'reports'
QUALITY_GRADES = ["casual", "needs_id", "research"]

# Initialize console
console = Console()

class MushroomObserver:
    def __init__(self):
        """Initialize the MushroomObserver class."""
        self.setup_logging()
        self.setup_directories()
        self.mushrooms = self.load_mushrooms()

    def setup_logging(self):
        """Configure logging."""
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        self.logger = logging.getLogger('mushroom_observer')
        self.logger.setLevel(logging.INFO)
        
        handler = RotatingFileHandler(
            'logs/mushroom_observer.log',
            maxBytes=1024 * 1024,
            backupCount=10
        )
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def setup_directories(self):
        """Create required directories."""
        for directory in [DATA_DIR, 'logs', REPORTS_DIR]:
            if not os.path.exists(directory):
                os.makedirs(directory)
                self.logger.info(f"Created directory: {directory}")

    def load_mushrooms(self):
        """Load mushrooms from text file."""
        mushrooms = {}
        if os.path.exists(MUSHROOM_FILE):
            with open(MUSHROOM_FILE, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            name, taxon_id = line.strip().split(',')
                            mushrooms[name] = int(taxon_id)
                        except ValueError as e:
                            self.logger.error(f"Invalid line in mushroom file: {line.strip()} - {e}")
        return dict(sorted(mushrooms.items()))

    def save_mushrooms(self):
        """Save mushrooms to text file."""
        try:
            with open(MUSHROOM_FILE, 'w') as f:
                for name, taxon_id in sorted(self.mushrooms.items()):
                    f.write(f"{name},{taxon_id}\n")
            return True
        except Exception as e:
            self.logger.error(f"Error saving mushrooms: {e}")
            return False

    def view_mushrooms(self):
        """Display list of tracked mushrooms."""
        console.clear()
        if not self.mushrooms:
            rprint("[yellow]No mushrooms in the list![/yellow]")
        else:
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Name", style="cyan")
            table.add_column("Taxon ID", style="green")
            
            for name, taxon_id in self.mushrooms.items():
                table.add_row(name, str(taxon_id))
            
            console.print(table)
        
        input("\nPress Enter to continue...")

    def add_mushroom(self):
        """Add a new mushroom to track."""
        console.clear()
        rprint("[bold]Add New Mushroom[/bold]")
        
        name = Prompt.ask("\nEnter mushroom name")
        if name in self.mushrooms:
            rprint("[red]This mushroom is already in the list![/red]")
            input("\nPress Enter to continue...")
            return
        
        try:
            taxon_id = int(Prompt.ask("Enter iNaturalist taxon ID"))
            self.mushrooms[name] = taxon_id
            if self.save_mushrooms():
                rprint("[green]Mushroom added successfully![/green]")
                
                rprint("[yellow]\nFetching initial observation data...[/yellow]")
                data = self.fetch_observations(taxon_id, name)
                if not data.empty:
                    rprint(f"[green]Successfully loaded {len(data)} observations for {name}[/green]")
                else:
                    rprint("[red]No observations found for this mushroom[/red]")
            else:
                rprint("[red]Error saving mushroom data![/red]")
        except ValueError:
            rprint("[red]Invalid taxon ID! Please enter a number.[/red]")
        
        input("\nPress Enter to continue...")

    def remove_mushroom(self):
        """Remove a mushroom from tracking."""
        console.clear()
        if not self.mushrooms:
            rprint("[yellow]No mushrooms to remove![/yellow]")
            input("\nPress Enter to continue...")
            return
        
        rprint("[bold]Remove Mushroom[/bold]\n")
        for i, name in enumerate(self.mushrooms.keys(), 1):
            rprint(f"{i}. {name}")
        
        try:
            choice = int(Prompt.ask("\nEnter number to remove (0 to cancel)"))
            if choice == 0:
                return
            if 1 <= choice <= len(self.mushrooms):
                name = list(self.mushrooms.keys())[choice-1]
                if Confirm.ask(f"Remove {name}?"):
                    del self.mushrooms[name]
                    if self.save_mushrooms():
                        rprint("[green]Mushroom removed successfully![/green]")
                    else:
                        rprint("[red]Error saving mushroom data![/red]")
            else:
                rprint("[red]Invalid choice![/red]")
        except ValueError:
            rprint("[red]Invalid input! Please enter a number.[/red]")
        
        input("\nPress Enter to continue...")

    def edit_mushroom(self):
        """Edit name or taxon ID for an existing mushroom."""
        console.clear()
        if not self.mushrooms:
            rprint("[yellow]No mushrooms to edit![/yellow]")
            input("\nPress Enter to continue...")
            return
        
        rprint("[bold]Edit Mushroom[/bold]\n")
        for i, (name, taxon_id) in enumerate(self.mushrooms.items(), 1):
            rprint(f"{i}. {name} (Taxon ID: {taxon_id})")
        
        try:
            choice = int(Prompt.ask("\nEnter number to edit (0 to cancel)"))
            if choice == 0:
                return
            if 1 <= choice <= len(self.mushrooms):
                old_name = list(self.mushrooms.keys())[choice-1]
                old_taxon_id = self.mushrooms[old_name]
                
                new_name = Prompt.ask("Enter new name (or press Enter to keep current)", default=old_name)
                new_taxon_str = Prompt.ask(
                    "Enter new taxon ID (or press Enter to keep current)",
                    default=str(old_taxon_id)
                )
                
                try:
                    new_taxon_id = int(new_taxon_str)
                    
                    if new_name != old_name:
                        del self.mushrooms[old_name]
                        old_cache = os.path.join(DATA_DIR, f'taxon_{old_taxon_id}.json')
                        if os.path.exists(old_cache):
                            os.rename(old_cache, os.path.join(DATA_DIR, f'taxon_{new_taxon_id}.json'))
                    
                    self.mushrooms[new_name] = new_taxon_id
                    
                    if self.save_mushrooms():
                        rprint("[green]Mushroom updated successfully![/green]")
                    else:
                        rprint("[red]Error saving mushroom data![/red]")
                except ValueError:
                    rprint("[red]Invalid taxon ID! Please enter a number.[/red]")
            else:
                rprint("[red]Invalid choice![/red]")
        except ValueError:
            rprint("[red]Invalid input! Please enter a number.[/red]")
        
        input("\nPress Enter to continue...")

    def validate_observation(self, observation):
        """Validate individual observation data."""
        try:
            if not all(field in observation for field in ['id', 'observed_on', 'geojson']):
                return False
            
            if not observation['observed_on'] or not observation['geojson']:
                return False
            
            coords = observation['geojson'].get('coordinates', [])
            if len(coords) != 2:
                return False
                
            lon, lat = coords
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                return False
            
            return True
        except Exception as e:
            self.logger.error(f"Error validating observation: {e}")
            return False

    def fetch_observations(self, taxon_id, mushroom_name=None):
        """Fetch observation data from iNaturalist API."""
        all_data = []
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task(f"Fetching data for {mushroom_name}...", total=None)
                
                # Check cache first
                cached_data = self.load_cached_data(taxon_id)
                if cached_data:
                    progress.update(task, description=f"Loaded cached data for {mushroom_name}")
                    return pd.DataFrame(cached_data)

                headers = {
                    "User-Agent": "MushroomObserver/1.0",  # Fixed typo in User-Agent
                    "Accept": "application/json"
                }

                try:
                    for place_id in PLACE_IDS:
                        for quality_grade in QUALITY_GRADES:
                            page = 1
                            while True:
                                try:
                                    url = f"{API_BASE_URL}/observations"
                                    params = {
                                        "taxon_id": taxon_id,
                                        "place_id": place_id,
                                        "per_page": 200,
                                        "page": page,
                                        "quality_grade": quality_grade,
                                        "photos": "true",
                                        "geo": "true"
                                    }
                                    
                                    response = requests.get(url, params=params, headers=headers, timeout=30)  # Added timeout
                                    response.raise_for_status()
                                    data = response.json()
                                    
                                    results = data.get('results', [])
                                    if not results:
                                        break
                                    
                                    for result in results:
                                        result['quality_grade'] = quality_grade
                                    
                                    valid_results = [obs for obs in results if self.validate_observation(obs)]
                                    all_data.extend(valid_results)
                                    
                                    progress.update(task, 
                                        description=f"Loaded {len(all_data)} observations for {mushroom_name} ({quality_grade})")
                                    
                                    if len(results) < 200:
                                        break
                                    
                                    page += 1
                                    time.sleep(API_RATE_LIMIT)
                                    
                                except requests.RequestException as e:
                                    self.logger.error(f"Error fetching page {page}: {e}")
                                    break
                                except KeyboardInterrupt:
                                    rprint("\n[yellow]Data fetch interrupted by user[/yellow]")
                                    break

                    if all_data:
                        self.save_cached_data(taxon_id, all_data)
                    
                    return pd.DataFrame(all_data)

                except Exception as e:
                    self.logger.error(f"Error fetching observations: {e}")
                    return pd.DataFrame()

        except KeyboardInterrupt:
            rprint("\n[yellow]Operation cancelled by user[/yellow]")
            return pd.DataFrame(all_data) if all_data else pd.DataFrame()
        except Exception as e:
            self.logger.error(f"Unexpected error in fetch_observations: {e}")
            return pd.DataFrame()

    def fetch_observations_since(self, taxon_id, mushroom_name, since_date=None):
        """Fetch only new observations since the given date."""
        all_data = []
        headers = {
            "User-Agent": "MushroomObserver/1.0",  # Fixed typo
            "Accept": "application/json"
        }

        try:
            # Convert since_date to proper format if it exists
            if since_date:
                # Ensure we're using a datetime object
                if isinstance(since_date, str):
                    since_date = pd.to_datetime(since_date)
                # Format for iNaturalist API
                since_date = since_date.strftime('%Y-%m-%d')
                
            for place_id in PLACE_IDS:
                for quality_grade in QUALITY_GRADES:
                    page = 1
                    while True:
                        try:
                            url = f"{API_BASE_URL}/observations"
                            params = {
                                "taxon_id": taxon_id,
                                "place_id": place_id,
                                "per_page": 200,
                                "page": page,
                                "quality_grade": quality_grade,
                                "photos": "true",
                                "geo": "true",
                                "order_by": "observed_on",
                                "order": "desc"  # Get newest first
                            }
                            
                            if since_date:
                                params["d1"] = since_date  # Date must be in YYYY-MM-DD format
                                self.logger.info(f"Fetching observations since {since_date}")

                            response = requests.get(url, params=params, headers=headers, timeout=30)
                            response.raise_for_status()
                            data = response.json()
                            
                            results = data.get('results', [])
                            if not results:
                                break
                            
                            # Add quality grade to each observation
                            for result in results:
                                result['quality_grade'] = quality_grade
                                
                            valid_results = [obs for obs in results if self.validate_observation(obs)]
                            
                            # Log the number of new observations found
                            if valid_results:
                                self.logger.info(f"Found {len(valid_results)} new observations for {mushroom_name}")
                            
                            all_data.extend(valid_results)
                            
                            if len(results) < 200:
                                break
                            
                            page += 1
                            time.sleep(API_RATE_LIMIT)
                            
                        except requests.RequestException as e:
                            self.logger.error(f"Error fetching page {page}: {e}")
                            break

            return all_data

        except Exception as e:
            self.logger.error(f"Error fetching new observations: {e}")
            return []

    def load_cached_data(self, taxon_id):
        """Load cached observation data."""
        cache_file = os.path.join(DATA_DIR, f'taxon_{taxon_id}.json')
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                return json.load(f)
        return None

    def save_cached_data(self, taxon_id, data):
        """Save observation data to cache."""
        cache_file = os.path.join(DATA_DIR, f'taxon_{taxon_id}.json')
        with open(cache_file, 'w') as f:
            json.dump(data, f)

    def calculate_monthly_totals(self, data):
        """Calculate monthly observation totals with historical breakdowns."""
        if 'observed_on' not in data.columns or data.empty:
            return pd.DataFrame(), pd.DataFrame()
        
        data['observed_on'] = pd.to_datetime(data['observed_on'])
        data['year'] = data['observed_on'].dt.year
        
        monthly_counts = data.groupby([
            data['observed_on'].dt.month,
            'quality_grade'
        ]).size().unstack(fill_value=0)
        
        historical_counts = data.groupby([
            data['observed_on'].dt.year,
            data['observed_on'].dt.month,
            'quality_grade'
        ]).size().unstack(fill_value=0)
        
        monthly_counts['Total'] = monthly_counts.sum(axis=1)
        historical_counts['Total'] = historical_counts.sum(axis=1)
        
        month_names = {
            1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
            7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
        }
        
        monthly_counts.index = monthly_counts.index.map(month_names)
        historical_counts.index = historical_counts.index.map(
            lambda x: f"{month_names[x[1]]} {x[0]}"
        )
        
        return monthly_counts, historical_counts

    def get_seasonal_predictions(self, all_mushroom_data):
        """Calculate seasonal predictions for mushroom occurrence."""
        current_date = datetime.datetime.now()
        current_month = current_date.month
        last_month = (current_month - 1) if current_month > 1 else 12
        next_month = (current_month + 1) if current_month < 12 else 1
        
        predictions = {}
        
        for name, data in all_mushroom_data.items():
            if data.empty or 'observed_on' not in data.columns:
                continue
                
            data['observed_on'] = pd.to_datetime(data['observed_on'])
            data['month'] = data['observed_on'].dt.month
            data['year'] = data['observed_on'].dt.year
            
            # Calculate monthly averages
            monthly_counts = data.groupby(['month']).size()
            yearly_counts = data.groupby(['year', 'month']).size()
            yearly_averages = yearly_counts.groupby('month').mean()
            
            # Calculate totals by month
            monthly_totals = monthly_counts.to_dict()
            
            predictions[name] = {
                'last_month': {
                    'month': last_month,
                    'avg': yearly_averages.get(last_month, 0),
                    'total': int(monthly_totals.get(last_month, 0))
                },
                'current_month': {
                    'month': current_month,
                    'avg': yearly_averages.get(current_month, 0),
                    'total': int(monthly_totals.get(current_month, 0))
                },
                'next_month': {
                    'month': next_month,
                    'avg': yearly_averages.get(next_month, 0),
                    'total': int(monthly_totals.get(next_month, 0))
                }
            }
        
        return predictions

    def manual_update_mushroom(self):
        """Manually update data for a specific mushroom."""
        console.clear()
        if not self.mushrooms:
            rprint("[yellow]No mushrooms to update![/yellow]")
            input("\nPress Enter to continue...")
            return
        
        rprint("[bold]Manual Mushroom Update[/bold]\n")
        for i, name in enumerate(self.mushrooms.keys(), 1):
            rprint(f"{i}. {name}")
        
        try:
            choice = int(Prompt.ask("\nEnter number to update (0 to cancel)"))
            if choice == 0:
                return
            if 1 <= choice <= len(self.mushrooms):
                name = list(self.mushrooms.keys())[choice-1]
                taxon_id = self.mushrooms[name]
                
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task(f"Fetching new data for {name}...")
                    
                    cache_file = os.path.join(DATA_DIR, f'taxon_{taxon_id}.json')
                    backup_file = os.path.join(DATA_DIR, f'taxon_{taxon_id}.json.bak')
                    
                    if os.path.exists(cache_file):
                        os.rename(cache_file, backup_file)
                    
                    try:
                        data = self.fetch_observations(taxon_id, name)
                        if not data.empty:
                            rprint(f"[green]Successfully updated {name} with {len(data)} observations[/green]")
                            
                            if os.path.exists(backup_file):
                                os.remove(backup_file)
                        else:
                            rprint("[red]No data retrieved. Restoring previous data...[/red]")
                            if os.path.exists(backup_file):
                                os.rename(backup_file, cache_file)
                    except Exception as e:
                        rprint(f"[red]Error updating data: {e}[/red]")
                        if os.path.exists(backup_file):
                            os.rename(backup_file, cache_file)
            else:
                rprint("[red]Invalid choice![/red]")
        except ValueError:
            rprint("[red]Invalid input! Please enter a number.[/red]")
        
        input("\nPress Enter to continue...")

    def generate_mushroom_report(self):
        """Generate report for a single mushroom."""
        console.clear()
        if not self.mushrooms:
            rprint("[yellow]No mushrooms to generate report for![/yellow]")
            input("\nPress Enter to continue...")
            return

        rprint("[bold]Generate Mushroom Report[/bold]\n")
        for i, name in enumerate(self.mushrooms.keys(), 1):
            rprint(f"{i}. {name}")
        
        try:
            choice = int(Prompt.ask("\nEnter number to generate report (0 to cancel)"))
            if choice == 0:
                return
            if 1 <= choice <= len(self.mushrooms):
                name = list(self.mushrooms.keys())[choice-1]
                taxon_id = self.mushrooms[name]
                
                with Progress(
                    SpinnerColumn(), 
                    TextColumn("[progress.description]{task.description}")
                ) as progress:
                    task = progress.add_task(f"Generating report for {name}...")
                    data = self.fetch_observations(taxon_id, name)
                    if not data.empty:
                        report_path = self.generate_report(data, name)
                        rprint(f"[green]Report generated: {report_path}[/green]")
                    else:
                        rprint("[red]No data available for this mushroom![/red]")
            else:
                rprint("[red]Invalid choice![/red]")
        except ValueError:
            rprint("[red]Invalid input! Please enter a number.[/red]")
        
        input("\nPress Enter to continue...")

    def generate_report(self, data, mushroom_name):
        """Generate HTML report with visualizations."""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_dir = os.path.join(REPORTS_DIR, f"{mushroom_name}_{timestamp}")
        os.makedirs(report_dir, exist_ok=True)

        m = folium.Map(location=DEFAULT_MAP_CENTER,
                    zoom_start=7,
                    width='100%',
                    height='100%')
        
        if not data.empty:
            locations = []
            for _, row in data.iterrows():
                if pd.notnull(row['geojson']):
                    coords = row['geojson']['coordinates']
                    locations.append([coords[1], coords[0]])  # Folium uses [lat, lon]
            
            if locations:
                HeatMap(locations).add_to(m)

        monthly_data, historical_data = self.calculate_monthly_totals(data)
        predictions = self.get_seasonal_predictions({mushroom_name: data})
        
        report_path = os.path.join(report_dir, 'report.html')
        self.create_html_report(
            report_path, 
            mushroom_name, 
            m, 
            monthly_data, 
            historical_data,
            predictions.get(mushroom_name, {}), 
            data
        )
        
        return report_path

    def create_consolidated_html_report(self, filepath, all_mushroom_data, consolidated_predictions):
        """Create consolidated HTML report for all mushrooms."""
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        all_stats = {}
        overall_summary = {
            'total_observations': 0,
            'most_active_month': None,
            'most_active_year': None,
            'quality_distribution': {},
            'yearly_trends': {}
        }

        for name, data in all_mushroom_data.items():
            if not data.empty:
                # Create heatmap for this mushroom
                m = folium.Map(location=DEFAULT_MAP_CENTER, 
                             zoom_start=7,
                             width='100%',
                             height='100%')
                locations = []
                for _, row in data.iterrows():
                    if pd.notnull(row['geojson']):
                        coords = row['geojson']['coordinates']
                        locations.append([coords[1], coords[0]])  # Folium uses [lat, lon]
                
                if locations:
                    HeatMap(locations).add_to(m)
                
                # Convert to datetime for analysis
                data['observed_on'] = pd.to_datetime(data['observed_on'])
                
                # Calculate statistics
                monthly_data, historical_data = self.calculate_monthly_totals(data)
                yearly_observations = data.groupby(data['observed_on'].dt.year).size()
                monthly_breakdown = data.groupby(data['observed_on'].dt.month).size()
                quality_grades = data['quality_grade'].value_counts()
                
                # Calculate year-over-year growth
                yearly_growth = yearly_observations.pct_change() * 100
                
                # Find peak months and years
                peak_month = monthly_breakdown.idxmax()
                peak_year = yearly_observations.idxmax()
                
                # Calculate relative frequency compared to other mushrooms
                total_obs = len(data)
                overall_summary['total_observations'] += total_obs
                
                # Update quality grade distribution
                for grade, count in quality_grades.items():
                    overall_summary['quality_distribution'][grade] = \
                        overall_summary['quality_distribution'].get(grade, 0) + count
                
                # Track yearly trends
                for year, count in yearly_observations.items():
                    overall_summary['yearly_trends'][year] = \
                        overall_summary['yearly_trends'].get(year, 0) + count
                
                all_stats[name] = {
                    'total_observations': total_obs,
                    'monthly_data': monthly_data,
                    'historical_data': historical_data,
                    'predictions': consolidated_predictions.get(name, {}),
                    'heatmap': m._repr_html_(),
                    'peak_month': peak_month,
                    'peak_year': peak_year,
                    'yearly_growth': yearly_growth,
                    'quality_breakdown': quality_grades,
                    'yearly_observations': yearly_observations
                }

        # Calculate overall trends
        overall_summary['most_active_year'] = max(overall_summary['yearly_trends'].items(), 
                                                key=lambda x: x[1])[0]
        
        # Generate HTML content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Enhanced Mushroom Report</title>
            <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css">
            <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
            <style>
                body {{ padding: 20px; background-color: #f5f5f5; }}
                .container {{ 
                    max-width: 1200px; 
                    background-color: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 0 20px rgba(0,0,0,0.1);
                }}
                h1, h2, h3 {{ 
                    color: #2c3e50;
                    margin-bottom: 20px;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #eee;
                }}
                .mushroom-section {{
                    margin-bottom: 40px;
                    padding: 20px;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    background-color: white;
                }}
                .map-container {{ 
                    height: 600px;
                    width: 100%;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    overflow: hidden;
                    margin: 20px 0;
                }}
                .summary-card {{
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                }}
                .trend-indicator {{
                    font-weight: bold;
                    padding: 2px 6px;
                    border-radius: 3px;
                }}
                .trend-up {{ color: #28a745; }}
                .trend-down {{ color: #dc3545; }}
                .leaflet-container {{
                    height: 100% !important;
                    width: 100% !important;
                    position: relative !important;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Consolidated Mushroom Report</h1>
                <p class="lead">Report generated on: {timestamp}</p>
                
                <div class="row mt-4">
                    <div class="col-12">
                        <h2>Overall Summary</h2>
                        <div class="summary-card">
                            <div class="row">
                                <div class="col-md-4">
                                    <h5>Total Observations</h5>
                                    <p class="h3">{overall_summary['total_observations']:,}</p>
                                </div>
                                <div class="col-md-4">
                                    <h5>Most Active Year</h5>
                                    <p class="h3">{overall_summary['most_active_year']}</p>
                                </div>
                                <div class="col-md-4">
                                    <h5>Quality Distribution</h5>
                                    {self._create_quality_distribution_html(overall_summary['quality_distribution'])}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {self._create_mushroom_sections(all_stats)}
            </div>

            <script>
                // Force Leaflet maps to update their size
                setTimeout(function() {{
                    document.querySelectorAll('.leaflet-container').forEach(function(map) {{
                        map._leaflet_map && map._leaflet_map.invalidateSize();
                    }});
                }}, 100);
            </script>
        </body>
        </html>
        """
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)

    def _create_mushroom_sections(self, all_stats):
        """Create HTML for all mushroom sections."""
        sections = []
        for name, stats in all_stats.items():
            try:
                yearly_trend = self._create_yearly_trend_chart(stats['yearly_observations'], name)
            except Exception as e:
                self.logger.error(f"Error creating trend chart for {name}: {e}")
                yearly_trend = "<div>Error generating trend chart</div>"

            section = f"""
                <div class="mushroom-section">
                    <h2>{name}</h2>
                    <div class="row">
                        <div class="col-md-4">
                            <div class="summary-card">
                                <h5>Quick Stats</h5>
                                <p>Peak Month: {self._get_month_name(stats['peak_month'])}<br>
                                Peak Year: {stats['peak_year']}<br>
                                Latest Growth: {stats['yearly_growth'].iloc[-1]:.1f}%</p>
                            </div>
                        </div>
                        <div class="col-md-8">
                            <div class="summary-card">
                                <h5>Yearly Trend</h5>
                                {yearly_trend}
                            </div>
                        </div>
                    </div>
                    
                    <div class="row">
                        <div class="col-12">
                            <h3>Observation Heatmap</h3>
                            <div class="map-container">
                                {stats['heatmap']}
                            </div>
                        </div>
                    </div>
                    
                    <div class="row">
                        <div class="col-12">
                            <h3>Monthly Patterns</h3>
                            <div class="table-responsive">
                                {stats['monthly_data'].to_html(classes='table table-striped')}
                            </div>
                        </div>
                    </div>
                    
                    <div class="row mt-4">
                        <div class="col-12">
                            <h3>Seasonal Predictions</h3>
                            <div class="card-deck">
                                {self._create_prediction_cards(stats['predictions'])}
                            </div>
                        </div>
                    </div>
                </div>"""
            sections.append(section)
        
        return '\n'.join(sections)
            
    def _get_month_name(self, month_num):
        """Convert month number to name."""
        months = {
            1: 'January', 2: 'February', 3: 'March',
            4: 'April', 5: 'May', 6: 'June',
            7: 'July', 8: 'August', 9: 'September',
            10: 'October', 11: 'November', 12: 'December'
        }
        return months.get(month_num, 'Unknown')            

    def _create_quality_distribution_html(self, distribution):
        """Create HTML for quality grade distribution."""
        total = sum(distribution.values())
        html = '<div class="quality-grades">'
        for grade, count in distribution.items():
            percentage = (count / total) * 100
            html += f'<div>{grade}: {percentage:.1f}%</div>'
        html += '</div>'
        return html

    def _create_yearly_trend_chart(self, yearly_data, name):
        """Create a yearly trend visualization."""
        # Convert data to lists for JSON serialization
        years = list(yearly_data.index)
        counts = list(yearly_data.values)
        
        return f"""
            <div id="trend-chart-{name.replace(' ', '-')}" style="height: 200px;"></div>
            <script>
                var chartData = {{
                    x: {years},
                    y: {counts},
                    type: 'scatter',
                    mode: 'lines+markers',
                    name: 'Observations'
                }};

                var chartLayout = {{
                    margin: {{
                        t: 20,
                        r: 20,
                        b: 40,
                        l: 40
                    }},
                    xaxis: {{
                        title: 'Year'
                    }},
                    yaxis: {{
                        title: 'Observations'
                    }}
                }};

                Plotly.newPlot('trend-chart-{name.replace(' ', '-')}', [chartData], chartLayout);
            </script>
        """

    def _create_prediction_cards(self, predictions):
        """Helper method to create prediction cards HTML."""
        month_names = {
            1: 'January', 2: 'February', 3: 'March', 4: 'April', 
            5: 'May', 6: 'June', 7: 'July', 8: 'August',
            9: 'September', 10: 'October', 11: 'November', 12: 'December'
        }
        
        cards_html = ""
        for period in ['last_month', 'current_month', 'next_month']:
            if period in predictions:
                pred = predictions[period]
                month_num = pred.get('month', 1)
                month_name = month_names.get(month_num, 'Unknown')
                
                # Get raw values directly
                total = pred.get('total', 0)
                avg = pred.get('avg', 0)
                
                cards_html += f"""
                    <div class="card">
                        <div class="card-body">
                            <h5 class="card-title">{month_name}</h5>
                            <p class="card-text">
                                Historical Average: {avg:.1f}<br>
                                All-time Total: {total:,}
                            </p>
                        </div>
                    </div>"""
        
        return cards_html

    def generate_consolidated_report(self):
        """Generate a consolidated report for all mushrooms."""
        console.clear()
        if not self.mushrooms:
            rprint("[yellow]No mushrooms to generate report for![/yellow]")
            input("\nPress Enter to continue...")
            return

        rprint("[bold]Generating Consolidated Report[/bold]\n")
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_dir = os.path.join(REPORTS_DIR, f"consolidated_{timestamp}")
        os.makedirs(report_dir, exist_ok=True)

        all_mushroom_data = {}
        consolidated_predictions = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}")
        ) as progress:
            task = progress.add_task("Collecting mushroom data...", total=len(self.mushrooms))
            
            for name, taxon_id in self.mushrooms.items():
                progress.update(task, description=f"Loading data for {name}")
                data = self.fetch_observations(taxon_id, name)
                if not data.empty:
                    all_mushroom_data[name] = data
                progress.advance(task)

            consolidated_predictions = self.get_seasonal_predictions(all_mushroom_data)

        if not all_mushroom_data:
            rprint("[red]No data available for any mushrooms![/red]")
            input("\nPress Enter to continue...")
            return

        report_path = os.path.join(report_dir, 'consolidated_report.html')
        self.create_consolidated_html_report(report_path, all_mushroom_data, consolidated_predictions)
        
        rprint(f"[green]Consolidated report generated: {report_path}[/green]")
        input("\nPress Enter to continue...")
        
    def create_html_report(self, filepath, mushroom_name, heatmap, monthly_data, historical_data, seasonal_pred, full_data):
        """Create enhanced HTML report with monthly totals and predictions."""
        quality_dist = full_data['quality_grade'].value_counts()
        monthly_totals = monthly_data.copy()
        grand_total = monthly_totals['Total'].sum()
        
        month_names = {
            1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June',
            7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'
        }

        seasonal_html = f"""
            <div class="row mt-4">
                <div class="col-12">
                    <h2>Seasonal Patterns</h2>
                    <div class="card-deck">
                        <div class="card">
                            <div class="card-body">
                                <h5 class="card-title">Last Month ({month_names[seasonal_pred['last_month']['month']]})</h5>
                                <p class="card-text">
                                    Historical Average: {seasonal_pred['last_month']['avg']:.1f}<br>
                                    All-time Total: {seasonal_pred['last_month']['total']}
                                </p>
                            </div>
                        </div>
                        <div class="card">
                            <div class="card-body">
                                <h5 class="card-title">Current Month ({month_names[seasonal_pred['current_month']['month']]})</h5>
                                <p class="card-text">
                                    Historical Average: {seasonal_pred['current_month']['avg']:.1f}<br>
                                    All-time Total: {seasonal_pred['current_month']['total']}
                                </p>
                            </div>
                        </div>
                        <div class="card">
                            <div class="card-body">
                                <h5 class="card-title">Next Month ({month_names[seasonal_pred['next_month']['month']]})</h5>
                                <p class="card-text">
                                    Historical Average: {seasonal_pred['next_month']['avg']:.1f}<br>
                                    All-time Total: {seasonal_pred['next_month']['total']}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        """

        quality_html = f"""
            <div class="row mt-4">
                <div class="col-12">
                    <h2>Quality Grade Distribution</h2>
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>Quality Grade</th>
                                <th>Count</th>
                                <th>Percentage</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(f"""
                                <tr>
                                    <td>{grade}</td>
                                    <td>{count}</td>
                                    <td>{(count/len(full_data)*100):.1f}%</td>
                                </tr>""" for grade, count in quality_dist.items())}
                        </tbody>
                    </table>
                </div>
            </div>
        """

        monthly_html = f"""
            <div class="row mt-4">
                <div class="col-12">
                    <h2>Monthly Observations</h2>
                    <div class="table-responsive">
                        {monthly_data.to_html(classes='table table-striped table-hover')}
                    </div>
                    <div class="mt-3">
                        <strong>Grand Total: {grand_total:,} observations</strong>
                    </div>
                </div>
            </div>
            
            <div class="row mt-4">
                <div class="col-12">
                    <h2>Historical Monthly Breakdown</h2>
                    <div class="table-responsive">
                        {historical_data.to_html(classes='table table-striped table-hover')}
                    </div>
                </div>
            </div>
        """

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{mushroom_name} Observation Report</title>
            <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css">
            <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
            <style>
                body {{ 
                    padding: 20px; 
                    background-color: #f5f5f5;
                }}
                .container {{ 
                    max-width: 1200px; 
                    background-color: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 0 20px rgba(0,0,0,0.1);
                }}
                .map-container {{ 
                    height: 600px;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    overflow: hidden;
                    margin: 20px 0;
                }}
                h1 {{ 
                    color: #2c3e50;
                    margin-bottom: 30px;
                    padding-bottom: 15px;
                    border-bottom: 2px solid #eee;
                }}
                h2 {{ 
                    color: #2c3e50;
                    margin: 30px 0 20px 0;
                    padding-bottom: 10px;
                    border-bottom: 1px solid #eee;
                }}
                .table {{ 
                    margin-bottom: 0;
                    background-color: white;
                }}
                .table-responsive {{ 
                    margin: 20px 0;
                    border-radius: 5px;
                    overflow: hidden;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                }}
                .card-deck {{
                    margin: 20px 0;
                }}
                .card {{
                    background-color: #f8f9fa;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{mushroom_name} Observation Report</h1>
                <div class="row">
                    <div class="col-12">
                        <p class="lead">Report generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                        <p>Total Observations: {len(full_data):,}</p>
                    </div>
                </div>
                
                {seasonal_html}
                
                <div class="row">
                    <div class="col-12">
                        <h2>Observation Heatmap</h2>
                        <div class="map-container">
                            {heatmap._repr_html_()}
                        </div>
                    </div>
                </div>

                {quality_html}
                {monthly_html}
                
                <div id="monthlyPlot" style="height: 500px; margin-top: 30px;"></div>
            </div>

            <script>
                var data = [];
                var months = {list(monthly_data.index.values)};
                
                for (let grade of ['research', 'needs_id', 'casual']) {{
                    if (grade in monthly_data.columns) {{
                        data.push({{
                            x: months,
                            y: monthly_data[grade].tolist(),
                            name: grade,
                            type: 'bar'
                        }});
                    }}
                }}

                var layout = {{
                    title: 'Monthly Observations by Quality Grade',
                    barmode: 'stack',
                    xaxis: {{ title: 'Month' }},
                    yaxis: {{ title: 'Number of Observations' }},
                    showlegend: true
                }};

                Plotly.newPlot('monthlyPlot', data, layout);
            </script>
        </body>
        </html>
        """
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)

    def update_mushroom_data(self):
        """Update observation data for all mushrooms, only fetching new data."""
        if not self.mushrooms:
            rprint("[yellow]No mushrooms available to update![/yellow]")
            input("\nPress Enter to continue...")
            return

        console.clear()
        rprint("[bold green]🍄 Updating Mushroom Data[/bold green]\n")
        
        total_new_observations = 0
        
        results_table = Table(
            title="Update Results",
            show_header=True,
            header_style="bold magenta"
        )
        results_table.add_column("Mushroom", style="cyan")
        results_table.add_column("Status", style="green")
        results_table.add_column("New Observations", justify="right", style="yellow")
        results_table.add_column("Total Observations", justify="right", style="blue")
        results_table.add_column("Quality Grades", style="magenta")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            overall_task = progress.add_task(
                "Updating mushrooms...", 
                total=len(self.mushrooms)
            )
            
            for name, taxon_id in self.mushrooms.items():
                progress.update(overall_task, description=f"Checking {name}")
                
                try:
                    cached_data = self.load_cached_data(taxon_id)
                    last_date = None
                    current_count = len(cached_data) if cached_data else 0
                    
                    if cached_data:
                        dates = [obs.get('observed_on') for obs in cached_data if obs.get('observed_on')]
                        if dates:
                            last_date = max(dates)
                            self.logger.info(f"Last observation date for {name}: {last_date}")
                    
                    new_data = self.fetch_observations_since(taxon_id, name, last_date)
                    
                    if new_data:
                        if cached_data:
                            existing_ids = {obs['id'] for obs in cached_data}
                            new_data = [obs for obs in new_data if obs['id'] not in existing_ids]
                            merged_data = cached_data + new_data
                        else:
                            merged_data = new_data
                        
                        if new_data:
                            self.save_cached_data(taxon_id, merged_data)
                            new_count = len(new_data)
                            total_new_observations += new_count
                            total_count = len(merged_data)
                            
                            quality_counts = {}
                            for obs in new_data:
                                grade = obs.get('quality_grade', 'unknown')
                                quality_counts[grade] = quality_counts.get(grade, 0) + 1
                            
                            quality_summary = ", ".join(f"{grade}: {count}" for grade, count in quality_counts.items())
                            status = "✓ Updated"
                        else:
                            status = "✓ No updates"
                            new_count = 0
                            total_count = current_count
                            quality_summary = "-"
                    else:
                        new_count = 0
                        total_count = current_count
                        status = "✓ No updates"
                        quality_summary = "-"
                    
                    results_table.add_row(
                        name,
                        status,
                        str(new_count),
                        str(total_count),
                        quality_summary
                    )
                    
                except Exception as e:
                    self.logger.error(f"Error updating {name}: {e}")
                    results_table.add_row(
                        name,
                        "[red]✗ Error[/red]",
                        "-",
                        str(current_count),
                        "-"
                    )
                
                progress.advance(overall_task)

            progress.update(overall_task, description="Update complete!")

        console.clear()
        rprint("[bold green]🍄 Update Complete![/bold green]\n")
        console.print(results_table)
        
        rprint(f"\n[bold]Summary:[/bold]")
        rprint(f"Total mushrooms checked: [cyan]{len(self.mushrooms)}[/cyan]")
        rprint(f"New observations added: [yellow]{total_new_observations}[/yellow]")
        rprint(f"Last updated: [blue]{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
        
        input("\nPress Enter to continue...")

    def purge_cache(self):
        """Clear all cached observation data."""
        console.clear()
        if Confirm.ask("[yellow]Are you sure you want to purge all cached data?[/yellow]"):
            try:
                for file in os.listdir(DATA_DIR):
                    if file.endswith('.json'):
                        os.remove(os.path.join(DATA_DIR, file))
                rprint("[green]Cache purged successfully![/green]")
            except Exception as e:
                self.logger.error(f"Error purging cache: {e}")
                rprint(f"[red]Error purging cache: {e}[/red]")
        input("\nPress Enter to continue...")

    def show_menu(self):
        """Display main menu."""
        console.clear()
        rprint("[bold green]🍄 Mushroom Observer[/bold green]")
        rprint("\nMain Menu:")
        rprint("1. View Mushroom List")
        rprint("2. Add Mushroom")
        rprint("3. Remove Mushroom")
        rprint("4. Generate Report")
        rprint("5. Generate Consolidated Report")
        rprint("6. Update All Data")
        rprint("7. Manual Update Mushroom")
        rprint("8. Edit Mushroom")
        rprint("9. Purge Cache")
        rprint("q. Quit")

    def run(self):
        """Main application loop."""
        while True:
            self.show_menu()
            choice = Prompt.ask(
                "Enter your choice", 
                choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "q"]
            )
            
            if choice == "q":
                break
            elif choice == "1":
                self.view_mushrooms()
            elif choice == "2":
                self.add_mushroom()
            elif choice == "3":
                self.remove_mushroom()
            elif choice == "4":
                self.generate_mushroom_report()
            elif choice == "5":
                self.generate_consolidated_report()
            elif choice == "6":
                self.update_mushroom_data()
            elif choice == "7":
                self.manual_update_mushroom()
            elif choice == "8":
                self.edit_mushroom()
            elif choice == "9":
                self.purge_cache()

def main():
    observer = MushroomObserver()
    observer.run()

if __name__ == "__main__":
    main()