"""
Players Registry
Manages CSV registry of Arena Leaderboard players with their rankings
"""

import csv
import os
import logging
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)


class PlayersRegistry:
    """Manages CSV registry of players and their Arena rankings"""
    
    CSV_HEADERS = ['PlayerId', 'PlayerName', 'Country', 'ArenaRank', 'LastUpdated']
    
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self._ensure_csv_exists()
    
    def _ensure_csv_exists(self):
        """Create CSV file with headers if it doesn't exist"""
        if not os.path.exists(self.csv_path):
            os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
                writer.writeheader()
            logger.info(f"Created new players registry: {self.csv_path}")
    
    def update_players(self, players_data: List[Tuple[int, str, str, int]]) -> Dict[str, int]:
        """
        Update players registry with new leaderboard data
        
        Args:
            players_data: List of tuples (player_id, player_name, country, arena_rank)
            
        Returns:
            Dictionary with update statistics
        """
        current_time = datetime.now().isoformat()
        existing_players = self._load_existing_players()
        
        updated_count = 0
        new_count = 0
        
        # Convert existing players to dict for faster lookup
        existing_dict = {int(player['PlayerId']): player for player in existing_players}
        
        # Process new player data
        updated_players = {}
        for player_id, player_name, country, arena_rank in players_data:
            player_record = {
                'PlayerId': str(player_id),
                'PlayerName': player_name,
                'Country': country,
                'ArenaRank': str(arena_rank),
                'LastUpdated': current_time
            }
            
            if player_id in existing_dict:
                # Check if any data changed
                existing = existing_dict[player_id]
                if (existing['PlayerName'] != player_name or 
                    existing['Country'] != country or 
                    existing['ArenaRank'] != str(arena_rank)):
                    updated_count += 1
                    logger.debug(f"Updated player {player_id}: {player_name}")
                else:
                    # No changes, keep existing timestamp
                    player_record['LastUpdated'] = existing['LastUpdated']
            else:
                new_count += 1
                logger.debug(f"New player {player_id}: {player_name}")
            
            updated_players[player_id] = player_record
        
        # Add existing players not in the new data (preserve historical data)
        for player_id, player_data in existing_dict.items():
            if player_id not in updated_players:
                updated_players[player_id] = player_data
        
        # Write updated data back to CSV
        self._write_players_to_csv(list(updated_players.values()))
        
        stats = {
            'total_players': len(updated_players),
            'new_players': new_count,
            'updated_players': updated_count,
            'unchanged_players': len(updated_players) - new_count - updated_count
        }
        
        logger.info(f"Registry update complete: {stats}")
        return stats
    
    def _load_existing_players(self) -> List[Dict[str, str]]:
        """Load existing players from CSV"""
        players = []
        try:
            with open(self.csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    players.append(row)
        except FileNotFoundError:
            logger.warning(f"CSV file not found: {self.csv_path}")
        except Exception as e:
            logger.error(f"Error reading CSV: {e}")
        
        return players
    
    def _write_players_to_csv(self, players: List[Dict[str, str]]):
        """Write players data to CSV file"""
        try:
            # Sort by ArenaRank (ascending)
            players.sort(key=lambda x: int(x['ArenaRank']) if x['ArenaRank'].isdigit() else float('inf'))
            
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
                writer.writeheader()
                writer.writerows(players)
                
        except Exception as e:
            logger.error(f"Error writing to CSV: {e}")
            raise
    
    def get_player_count(self) -> int:
        """Get total number of players in registry"""
        players = self._load_existing_players()
        return len(players)
    
    def get_top_players(self, n: int = 10) -> List[Dict[str, str]]:
        """Get top N players by Arena rank"""
        players = self._load_existing_players()
        # Sort by ArenaRank
        players.sort(key=lambda x: int(x['ArenaRank']) if x['ArenaRank'].isdigit() else float('inf'))
        return players[:n]
    
    def find_player(self, player_id: int) -> Optional[Dict[str, str]]:
        """Find a specific player by ID"""
        players = self._load_existing_players()
        for player in players:
            if int(player['PlayerId']) == player_id:
                return player
        return None
    
    def get_players_by_country(self, country: str) -> List[Dict[str, str]]:
        """Get all players from a specific country"""
        players = self._load_existing_players()
        country_players = [p for p in players if p['Country'].lower() == country.lower()]
        # Sort by ArenaRank
        country_players.sort(key=lambda x: int(x['ArenaRank']) if x['ArenaRank'].isdigit() else float('inf'))
        return country_players
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get statistics about the players registry"""
        players = self._load_existing_players()
        
        if not players:
            return {'total_players': 0}
        
        countries = {}
        ranks = []
        last_updated_times = []
        
        for player in players:
            # Count by country
            country = player['Country']
            countries[country] = countries.get(country, 0) + 1
            
            # Collect ranks
            if player['ArenaRank'].isdigit():
                ranks.append(int(player['ArenaRank']))
            
            # Collect update times
            if player['LastUpdated']:
                try:
                    last_updated_times.append(datetime.fromisoformat(player['LastUpdated']))
                except ValueError:
                    pass
        
        stats = {
            'total_players': len(players),
            'countries_count': len(countries),
            'top_countries': sorted(countries.items(), key=lambda x: x[1], reverse=True)[:5],
            'rank_range': (min(ranks), max(ranks)) if ranks else (0, 0),
            'last_update': max(last_updated_times).isoformat() if last_updated_times else None
        }
        
        return stats
