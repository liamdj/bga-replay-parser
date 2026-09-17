"""
Master Games Registry Manager

Handles the centralized registry of all scraped games to prevent duplicates
and maintain a comprehensive overview of all processed games.
"""

import csv
import os
from datetime import datetime
from typing import Dict, List, Optional, Set


class GamesRegistry:
    """Manages the master games registry CSV file"""
    
    def __init__(self, registry_path: str = None):
        if registry_path is None:
            from . import constants
            registry_path = os.path.join(constants.REGISTRY_DATA_DIR, "games.csv")
        self.registry_path = registry_path
        self.fieldnames = [
            'TableId', 'PlayerPerspective', 'RawDatetime', 'ParsedDatetime', 'Players', 
            'IsArenaMode', 'Version', 'ScrapedAt', 'ParsedAt'
        ]
        self.registry_data = {}
        self.load_registry()
    
    def load_registry(self) -> None:
        """Load the master games registry from CSV file"""
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, 'r', encoding='utf-8', newline='') as f:
                    reader = csv.DictReader(f)
                    self.registry_data = {}
                    for row in reader:
                        table_id = row['TableId']
                        player_perspective = row.get('PlayerPerspective', '') if row.get('PlayerPerspective') else None
                        
                        # Create composite key: table_id + player_perspective
                        # For backward compatibility, if no player_perspective, use table_id only
                        if player_perspective:
                            composite_key = f"{table_id}_{player_perspective}"
                        else:
                            composite_key = table_id
                        
                        # Convert string values back to appropriate types
                        processed_row = {
                            'table_id': table_id,
                            'raw_datetime': row['RawDatetime'],
                            'parsed_datetime': row['ParsedDatetime'],
                            'players': row['Players'].split('|') if row['Players'] else [],
                            'is_arena_mode': bool(int(row['IsArenaMode'])) if row['IsArenaMode'] else False,
                            'version': row.get('Version', '') if row.get('Version') else None,
                            'scraped_at': row['ScrapedAt'] if row['ScrapedAt'] else None,
                            'parsed_at': row['ParsedAt'] if row['ParsedAt'] else None,
                            'player_perspective': player_perspective
                        }
                        self.registry_data[composite_key] = processed_row
            except (IOError, csv.Error) as e:
                print(f"Warning: Could not load registry file: {e}")
                self._create_empty_registry()
        else:
            self._create_empty_registry()
    
    def _create_empty_registry(self) -> None:
        """Create an empty registry structure"""
        self.registry_data = {}
        # Create empty CSV file with headers
        self.save_registry()
    
    def save_registry(self) -> None:
        """Save the registry to CSV file"""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        
        # Write to CSV file
        with open(self.registry_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writeheader()
            
            for composite_key, game_data in self.registry_data.items():
                # Convert data back to CSV format
                # Use the actual table_id from game_data, not the composite key
                csv_row = {
                    'TableId': game_data['table_id'],
                    'PlayerPerspective': game_data.get('player_perspective', '') if game_data.get('player_perspective') else '',
                    'RawDatetime': game_data['raw_datetime'],
                    'ParsedDatetime': game_data['parsed_datetime'],
                    'Players': '|'.join(str(pid) for pid in game_data['players']),
                    'IsArenaMode': '1' if game_data['is_arena_mode'] else '0',
                    'Version': game_data.get('version', '') if game_data.get('version') else '',
                    'ScrapedAt': game_data['scraped_at'] if game_data['scraped_at'] else '',
                    'ParsedAt': game_data['parsed_at'] if game_data['parsed_at'] else ''
                }
                writer.writerow(csv_row)
    
    def add_game_check(self, table_id: str, raw_datetime: str, parsed_datetime: str, 
                      players: List[str], is_arena_mode: bool = True, version: Optional[str] = None, 
                      player_perspective: Optional[str] = None) -> None:
        """Add a game check entry (called when encountering any game, even if skipped)"""
        # Create composite key
        if player_perspective:
            composite_key = f"{table_id}_{player_perspective}"
        else:
            composite_key = table_id
        
        game_entry = {
            'table_id': table_id,
            'raw_datetime': raw_datetime,
            'parsed_datetime': parsed_datetime,
            'players': [str(pid) for pid in players],  # Ensure all are strings
            'is_arena_mode': is_arena_mode,
            'version': version,
            'scraped_at': None,
            'parsed_at': None,
            'player_perspective': player_perspective
        }
        
        self.registry_data[composite_key] = game_entry
    
    def mark_game_scraped(self, table_id: str, scraped_at: Optional[str] = None, 
                         player_perspective: Optional[str] = None) -> None:
        """Mark a game as successfully scraped"""
        if scraped_at is None:
            scraped_at = datetime.now().isoformat()
        
        # Create composite key
        if player_perspective:
            composite_key = f"{table_id}_{player_perspective}"
        else:
            composite_key = table_id
        
        if composite_key in self.registry_data:
            self.registry_data[composite_key]['scraped_at'] = scraped_at
            if player_perspective:
                self.registry_data[composite_key]['player_perspective'] = player_perspective
        else:
            # If game wasn't checked before, create minimal entry
            self.registry_data[composite_key] = {
                'table_id': table_id,
                'raw_datetime': '',
                'parsed_datetime': '',
                'players': [],
                'is_arena_mode': True,  # Default assumption
                'scraped_at': scraped_at,
                'parsed_at': None,
                'player_perspective': player_perspective
            }
    
    def mark_game_parsed(self, table_id: str, parsed_at: Optional[str] = None, 
                        player_perspective: Optional[str] = None) -> None:
        """Mark a game as successfully parsed"""
        parsed_at = datetime.now().isoformat()
        
        # Create composite key
        if player_perspective:
            composite_key = f"{table_id}_{player_perspective}"
        else:
            composite_key = table_id
        
        # Try to find the game entry (check both composite key and table_id only)
        game_entry = None
        if composite_key in self.registry_data:
            game_entry = self.registry_data[composite_key]
        elif table_id in self.registry_data:
            game_entry = self.registry_data[table_id]
        else:
            # Look for any entry with this table_id
            for key, data in self.registry_data.items():
                if data.get('table_id') == table_id:
                    game_entry = data
                    composite_key = key
                    break
        
        if game_entry:
            game_entry['parsed_at'] = parsed_at
        else:
            # If game wasn't tracked before, create minimal entry
            self.registry_data[composite_key] = {
                'table_id': table_id,
                'raw_datetime': '',
                'parsed_datetime': '',
                'players': [],
                'is_arena_mode': True,  # Default assumption
                'scraped_at': None,
                'parsed_at': parsed_at,
                'player_perspective': player_perspective
            }
    
    def is_game_checked(self, table_id: str, player_perspective: Optional[str] = None) -> bool:
        """Check if a game has been encountered/checked before"""
        if player_perspective:
            composite_key = f"{table_id}_{player_perspective}"
        else:
            composite_key = table_id
        return composite_key in self.registry_data
    
    def is_game_scraped(self, table_id: str, player_perspective: Optional[str] = None) -> bool:
        """Check if a game has been successfully scraped"""
        if player_perspective:
            composite_key = f"{table_id}_{player_perspective}"
        else:
            composite_key = table_id
        
        if composite_key not in self.registry_data:
            return False
        return self.registry_data[composite_key]['scraped_at'] is not None
    
    def is_game_parsed(self, table_id: str, player_perspective: Optional[str] = None) -> bool:
        """Check if a game has been successfully parsed"""
        if player_perspective:
            composite_key = f"{table_id}_{player_perspective}"
        else:
            composite_key = table_id
        
        if composite_key not in self.registry_data:
            return False
        return self.registry_data[composite_key]['parsed_at'] is not None
    
    def get_scraped_game_ids(self) -> Set[str]:
        """Get set of all scraped game IDs"""
        return {
            table_id for table_id, game_data in self.registry_data.items()
            if game_data['scraped_at'] is not None
        }
    
    def get_checked_game_ids(self) -> Set[str]:
        """Get set of all checked game IDs (including unscraped ones)"""
        return set(self.registry_data.keys())
    
    def get_arena_games(self) -> Dict[str, Dict]:
        """Get only arena mode games"""
        return {
            table_id: game_data 
            for table_id, game_data in self.registry_data.items()
            if game_data['is_arena_mode']
        }
    
    def add_game(self, table_id: str, raw_datetime: str, parsed_datetime: str, 
                 players: List[Dict], scraped_by_player: str = None) -> None:
        """Add a game to the registry (legacy method for backward compatibility)"""
        # Extract player IDs from player objects
        player_ids = []
        for player in players:
            if isinstance(player, dict):
                player_ids.append(str(player.get('player_id', '')))
            else:
                player_ids.append(str(player))
        
        # Create or update entry
        if table_id in self.registry_data:
            # Update existing entry
            self.registry_data[table_id].update({
                'raw_datetime': raw_datetime,
                'parsed_datetime': parsed_datetime,
                'players': player_ids,
                'scraped_at': datetime.now().isoformat(),
                'parsed_at': datetime.now().isoformat(),  # Assume parsed if using legacy method
                'player_perspective': scraped_by_player
            })
        else:
            # Create new entry
            game_entry = {
                'table_id': table_id,
                'raw_datetime': raw_datetime,
                'parsed_datetime': parsed_datetime,
                'players': player_ids,
                'is_arena_mode': True,  # Default assumption for legacy calls
                'scraped_at': datetime.now().isoformat(),
                'parsed_at': datetime.now().isoformat(),
                'player_perspective': scraped_by_player
            }
            self.registry_data[table_id] = game_entry
    
    def mark_game_failed(self, table_id: str, error_reason: str, 
                        scraped_by_player: str = None) -> None:
        """Mark a game as failed to scrape (legacy method for backward compatibility)"""
        if table_id in self.registry_data:
            # Keep existing data but don't mark as scraped
            pass
        else:
            # Create minimal entry for failed game
            game_entry = {
                'table_id': table_id,
                'raw_datetime': '',
                'parsed_datetime': '',
                'players': [],
                'is_arena_mode': True,
                'scraped_at': None,
                'parsed_at': None,
                'player_perspective': scraped_by_player
            }
            self.registry_data[table_id] = game_entry
    
    def update_game_version(self, table_id: str, version: str) -> None:
        """Update the version number for an existing game"""
        if table_id in self.registry_data:
            self.registry_data[table_id]['version'] = version
        else:
            # Create minimal entry if game doesn't exist
            self.registry_data[table_id] = {
                'table_id': table_id,
                'raw_datetime': '',
                'parsed_datetime': '',
                'players': [],
                'is_arena_mode': True,
                'version': version,
                'scraped_at': None,
                'parsed_at': None,
                'player_perspective': None
            }

    def is_table_checked(self, table_id: str) -> bool:
        """Check if a table has been checked for Arena mode (regardless of player perspective)"""
        # Check if there's any entry for this table_id (with or without player perspective)
        for composite_key in self.registry_data.keys():
            if composite_key == table_id or composite_key.startswith(f"{table_id}_"):
                return True
        return False
    
    def is_replay_scraped(self, table_id: str, player_perspective: str) -> bool:
        """Check if a replay has been scraped for a specific player perspective"""
        composite_key = f"{table_id}_{player_perspective}"
        if composite_key not in self.registry_data:
            return False
        return self.registry_data[composite_key]['scraped_at'] is not None

    def get_game_info(self, table_id: str, player_perspective: Optional[str] = None) -> Optional[Dict]:
        """Get information about a specific game"""
        if player_perspective:
            composite_key = f"{table_id}_{player_perspective}"
        else:
            composite_key = table_id
        return self.registry_data.get(composite_key)
    
    def get_all_games(self) -> Dict[str, Dict]:
        """Get all games in the registry"""
        return self.registry_data
    
    def get_successful_games(self) -> Dict[str, Dict]:
        """Get only successfully scraped games"""
        return {
            table_id: game_data 
            for table_id, game_data in self.registry_data.items()
            if game_data['scraped_at'] is not None
        }
    
    def get_failed_games(self) -> Dict[str, Dict]:
        """Get games that were checked but not successfully scraped"""
        return {
            table_id: game_data 
            for table_id, game_data in self.registry_data.items()
            if game_data['scraped_at'] is None
        }
    
    def filter_new_games(self, game_list: List[Dict], player_perspective: Optional[str] = None) -> List[Dict]:
        """Filter out games that have already been scraped for the given player perspective"""
        return [
            game for game in game_list 
            if not self.is_game_scraped(game.get("table_id"), player_perspective)
        ]
    
    def filter_unchecked_games(self, game_list: List[Dict], player_perspective: Optional[str] = None) -> List[Dict]:
        """Filter out games that have already been checked for the given player perspective"""
        return [
            game for game in game_list 
            if not self.is_game_checked(game.get("table_id"), player_perspective)
        ]
    
    def filter_new_games_legacy(self, game_list: List[Dict]) -> List[Dict]:
        """Filter out games that have already been scraped (legacy method - table ID only)"""
        scraped_ids = self.get_scraped_game_ids()
        return [
            game for game in game_list 
            if game.get("table_id") not in scraped_ids
        ]
    
    def filter_unchecked_games_legacy(self, game_list: List[Dict]) -> List[Dict]:
        """Filter out games that have already been checked (legacy method - table ID only)"""
        checked_ids = self.get_checked_game_ids()
        return [
            game for game in game_list 
            if game.get("table_id") not in checked_ids
        ]
    
    def get_stats(self) -> Dict:
        """Get registry statistics"""
        all_games = self.registry_data
        scraped_games = self.get_successful_games()
        failed_games = self.get_failed_games()
        arena_games = self.get_arena_games()
        parsed_games = {
            table_id: game_data 
            for table_id, game_data in self.registry_data.items()
            if game_data['parsed_at'] is not None
        }
        
        return {
            "total_games": len(all_games),
            "scraped_games": len(scraped_games),
            "parsed_games": len(parsed_games),
            "failed_games": len(failed_games),
            "arena_games": len(arena_games),
            "scrape_success_rate": (len(scraped_games) / len(all_games) * 100) if all_games else 0,
            "parse_success_rate": (len(parsed_games) / len(scraped_games) * 100) if scraped_games else 0
        }
    
    def print_stats(self) -> None:
        """Print registry statistics"""
        stats = self.get_stats()
        print(f"\n=== Master Games Registry Stats ===")
        print(f"Total games tracked: {stats['total_games']}")
        print(f"Successfully scraped: {stats['scraped_games']}")
        print(f"Successfully parsed: {stats['parsed_games']}")
        print(f"Failed/skipped: {stats['failed_games']}")
        print(f"Arena mode games: {stats['arena_games']}")
        print(f"Scrape success rate: {stats['scrape_success_rate']:.1f}%")
        print(f"Parse success rate: {stats['parse_success_rate']:.1f}%")
