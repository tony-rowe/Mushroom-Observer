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
DEFAULT_MAP_CENTER = [43.8041, -120.5542]  # Oregon/Washington center
REPORTS_DIR = 'reports'
QUALITY_GRADES = ["casual", "needs_id", "research"]

# Initialize console
console = Console()

class MushroomObserver:
    def __init__(self):
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
                
                # Add this section to automatically fetch data
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
                
                with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
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
                    "User-Agent": "MuchroomObserver/1.0",
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
                                    
                                    response = requests.get(url, params=params, headers=headers)
                                    response.raise_for_status()
                                    data = response.json()
                                    
                                    results = data.get('results', [])
                                    if not results:
                                        break
                                    
                                    # Add quality_grade to each observation
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

                    # Save to cache if we got any data
                    if all_data:
                        self.save_cached_data(taxon_id, all_data)
                    
                    return pd.DataFrame(all_data)

                except Exception as e:
                    self.logger.error(f"Error fetching observations: {e}")
                    return pd.DataFrame()

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

    def fetch_observations_since(self, taxon_id, mushroom_name, since_date=None):
        """Fetch only new observations since the given date."""
        all_data = []
        headers = {
            "User-Agent": "MuchroomObserver/1.0",
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
                                "geo": "true",
                                "order_by": "observed_on",
                                "order": "desc"  # Get newest first
                            }
                            
                            # Add date filter if we have a last observation date
                            if since_date:
                                params["d1"] = since_date  # Only get observations after this date

                            response = requests.get(url, params=params, headers=headers)
                            response.raise_for_status()
                            data = response.json()
                            
                            results = data.get('results', [])
                            if not results:
                                break
                            
                            # Add quality_grade to each observation
                            for result in results:
                                result['quality_grade'] = quality_grade
                                
                            valid_results = [obs for obs in results if self.validate_observation(obs)]
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
    def generate_report(self, data, mushroom_name):
            """Generate HTML report with visualizations."""
            # Create report directory with timestamp
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            report_dir = os.path.join(REPORTS_DIR, f"{mushroom_name}_{timestamp}")
            os.makedirs(report_dir, exist_ok=True)

            # Generate heatmap
            m = folium.Map(location=DEFAULT_MAP_CENTER, zoom_start=6)
            
            if not data.empty:
                locations = []
                for _, row in data.iterrows():
                    if pd.notnull(row['geojson']):
                        coords = row['geojson']['coordinates']
                        locations.append([coords[1], coords[0]])  # Folium uses [lat, lon]
                
                if locations:
                    HeatMap(locations).add_to(m)

            # Calculate monthly statistics
            monthly_data = self.calculate_monthly_totals(data)
            
            # Generate HTML report
            report_path = os.path.join(report_dir, 'report.html')
            self.create_html_report(report_path, mushroom_name, m, monthly_data, data)
            
            return report_path

    def calculate_monthly_totals(self, data):
        """Calculate monthly observation totals."""
        if 'observed_on' in data.columns:
            data['observed_on'] = pd.to_datetime(data['observed_on'])
            monthly_counts = data.groupby([data['observed_on'].dt.month, 'quality_grade']).size().unstack(fill_value=0)
            
            month_names = {
                1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
                7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
            }
            monthly_counts.index = monthly_counts.index.map(month_names)
            
            # Add total column
            monthly_counts['Total'] = monthly_counts.sum(axis=1)
            
            return monthly_counts
        return pd.DataFrame()

    def create_html_report(self, filepath, mushroom_name, heatmap, monthly_data, full_data):
        """Create HTML report file."""
        # Calculate quality grade distribution
        quality_dist = full_data['quality_grade'].value_counts()
        
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

        # Create monthly observations table with quality grades
        monthly_html = f"""
            <div class="row mt-4">
                <div class="col-12">
                    <h2>Monthly Observations by Quality Grade</h2>
                    <div class="table-responsive">
                        {monthly_data.to_html(classes='table table-striped table-hover')}
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
                // Create monthly observations plot
                var data = [];
                var months = {list(monthly_data.index.values)};
                
                {'''
                for (let grade of ['research', 'needs_id', 'casual']) {
                    if (grade in monthly_data.columns) {
                        data.push({
                            x: months,
                            y: monthly_data[grade].tolist(),
                            name: grade,
                            type: 'bar'
                        });
                    }
                }
                '''}

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
            
            total_new_observations = 0  # Track total new observations
            
            # Create a table for results
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
                        # Get last observation date from cache
                        cached_data = self.load_cached_data(taxon_id)
                        last_date = None
                        current_count = len(cached_data) if cached_data else 0
                        
                        if cached_data:
                            dates = [obs.get('observed_on') for obs in cached_data if obs.get('observed_on')]
                            if dates:
                                last_date = max(dates)
                        
                        # Fetch new observations
                        new_data = self.fetch_observations_since(taxon_id, name, last_date)
                        
                        if new_data:
                            if cached_data:
                                # Remove any duplicates based on observation ID
                                existing_ids = {obs['id'] for obs in cached_data}
                                new_data = [obs for obs in new_data if obs['id'] not in existing_ids]
                                merged_data = cached_data + new_data
                            else:
                                merged_data = new_data
                            
                            # Save updated data
                            self.save_cached_data(taxon_id, merged_data)
                            new_count = len(new_data)
                            total_new_observations += new_count
                            total_count = len(merged_data)
                            
                            # Count quality grades in new data
                            quality_counts = {}
                            for obs in new_data:
                                grade = obs.get('quality_grade', 'unknown')
                                quality_counts[grade] = quality_counts.get(grade, 0) + 1
                            
                            quality_summary = ", ".join(f"{grade}: {count}" for grade, count in quality_counts.items())
                            status = "✓ Updated"
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

                # Update progress description
                progress.update(overall_task, description="Update complete!")

            # Show final results
            console.clear()
            rprint("[bold green]🍄 Update Complete![/bold green]\n")
            console.print(results_table)
            
            # Show summary
            rprint(f"\n[bold]Summary:[/bold]")
            rprint(f"Total mushrooms checked: [cyan]{len(self.mushrooms)}[/cyan]")
            rprint(f"New observations added: [yellow]{total_new_observations}[/yellow]")
            rprint(f"Last updated: [blue]{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
            
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
        rprint("6. Update Data")
        rprint("7. Purge Cache")
        rprint("q. Quit")

    def run(self):
        """Main application loop."""
        while True:
            self.show_menu()
            choice = Prompt.ask("Enter your choice", choices=["1", "2", "3", "4", "5", "6", "7", "q"])
            
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
                self.purge_cache()
def main():
    observer = MushroomObserver()
    observer.run()

if __name__ == "__main__":
    main()