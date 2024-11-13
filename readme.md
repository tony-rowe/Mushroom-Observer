# 🍄 Mushroom Observer

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![iNaturalist](https://img.shields.io/badge/Data-iNaturalist-green.svg)](https://www.inaturalist.org/)

A powerful tool for tracking and analyzing mushroom observations using iNaturalist data. Monitor seasonal patterns, generate detailed reports, and visualize mushroom distributions with interactive heatmaps.

## ✨ Features

- 🗺️ Interactive heatmaps showing observation distributions
- 📊 Detailed monthly statistics and quality grade analysis
- 🔮 Seasonal prediction system for mushroom appearances
- 📈 Historical data tracking and trend analysis
- 🔄 Automated data updates with manual override options
- 📑 Comprehensive HTML reports with visualizations
- 💾 Efficient data caching system

## 🚀 Getting Started

### Prerequisites

```bash
python -m pip install -r requirements.txt
```

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/mushroom-observer.git
cd mushroom-observer
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure the application (see Configuration section)

4. Run the application:
```bash
python mushroom_observer.py
```

## 🔧 Configuration

### Essential Settings
The following variables can be modified in the script to customize the application:

```python
# Location Settings
PLACE_IDS = [10]  # Default: Oregon (10)
# Find your place ID at: https://www.inaturalist.org/places/
# Common Place IDs:
# - Oregon: 10
# - Washington: 11
# - California: 14
# Multiple areas can be added: PLACE_IDS = [10, 11, 14]

# Map Display Settings
DEFAULT_MAP_CENTER = [43.8041, -120.5542]  # Default: Oregon center
# Format: [latitude, longitude]
# Common centers:
# - Oregon: [43.8041, -120.5542]
# - Washington: [47.7511, -120.7401]
# - California: [36.7783, -119.4179]

# API Settings
API_RATE_LIMIT = 0.5  # Seconds between requests
API_BASE_URL = 'https://api.inaturalist.org/v1'

# Cache Settings
CACHE_TIMEOUT = 43200  # 12 hours in seconds
DATA_DIR = 'mushroom_data'  # Cache directory
```

### Search Area Configuration
To modify the search area:
1. Visit [iNaturalist Places](https://www.inaturalist.org/places/)
2. Search for your desired location
3. The place ID is in the URL (e.g., `/places/10` for Oregon)
4. Update `PLACE_IDS` with your desired location(s)

### Map Center Configuration
To change the default map center:
1. Find your desired coordinates using [Google Maps](https://www.google.com/maps)
2. Right-click on the location and copy the coordinates
3. Update `DEFAULT_MAP_CENTER` with [latitude, longitude]

### API Configuration
The application uses the iNaturalist API v1. By default, it:
- Respects rate limits (0.5 seconds between requests)
- Caches data for 12 hours
- Uses the public API endpoint

To modify API behavior:
1. Adjust `API_RATE_LIMIT` for faster/slower requests
2. Change `CACHE_TIMEOUT` for different cache duration
3. Update `API_BASE_URL` if endpoint changes

## 📝 Usage Guide

### Adding Mushrooms
1. Select "Add Mushroom" from the main menu
2. You'll need:
   - Mushroom name (for your reference)
   - iNaturalist taxon ID
   
To find a taxon ID:
1. Search for the species on [iNaturalist](https://www.inaturalist.org)
2. The taxon ID is in the URL (e.g., `/taxa/48978`)

### Generating Reports
Individual Reports:
1. Select "Generate Report"
2. Choose a mushroom
3. Report includes:
   - Heatmap of observations
   - Monthly statistics
   - Quality grade distribution
   - Seasonal predictions

Consolidated Reports:
1. Select "Generate Consolidated Report"
2. Includes all tracked mushrooms in one report

### Data Management
Update Options:
- "Update All Data": Updates all mushrooms
- "Manual Update": Force update single mushroom
- "Purge Cache": Clear all cached data

Cache System:
- Data is cached in `DATA_DIR`
- Each mushroom has its own cache file
- Cache expires based on `CACHE_TIMEOUT`

## 📊 Report Features

### Heatmap
- Shows observation density
- Interactive zoom and pan
- Color intensity indicates observation frequency

### Statistics
- Monthly observation totals
- Quality grade distribution
- Historical trends
- Year-over-year comparisons

### Seasonal Predictions
- Based on historical data
- Shows likely appearance times
- Includes confidence levels

## 🚦 Troubleshooting

Common Issues:
1. **No Data Loading**
   - Check internet connection
   - Verify taxon ID exists
   - Ensure place ID is correct

2. **Slow Performance**
   - Check `API_RATE_LIMIT`
   - Verify internet speed
   - Consider reducing search area

3. **Map Not Displaying**
   - Check coordinates in `DEFAULT_MAP_CENTER`
   - Verify data exists for location
   - Check browser compatibility

## 📦 Dependencies

- folium (mapping)
- pandas (data analysis)
- requests (API calls)
- rich (terminal interface)
- plotly (data visualization)

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Data provided by [iNaturalist](https://www.inaturalist.org/)
- Mapping functionality powered by [Folium](https://python-visualization.github.io/folium/)
- Terminal interface created with [Rich](https://rich.readthedocs.io/)

## 📫 Contact

Your Name - [@yourtwitter](https://twitter.com/yourtwitter) - email@example.com

P