"""
Leaderboard Scraper
Fetches Arena Leaderboard data from BoardGameArena
"""

import logging
from typing import List, Tuple, Optional
from .bga_session import BGASession

logger = logging.getLogger(__name__)


class LeaderboardScraper:
    """Scrapes Arena Leaderboard data from BGA"""
    
    RANKING_URL = '/gamepanel/gamepanel/getRanking.html'
    
    def __init__(self, session: BGASession):
        """
        Args:
            session: BGASession instance
        """
        self.session = session
    
    def get_players_by_rank(self, game_id: int, num_players: int = 100,
                             mode: str = "arena") -> List[Tuple[int, str, str, int]]:
        """
        Fetch top N players from BGA leaderboard.

        Args:
            game_id: BGA game ID (e.g., 1118 for Terra Mystica)
            num_players: Number of top players to fetch
            mode: "arena" for the season Arena leaderboard (sparse for
                  smaller games), "elo" for the all-time overall ELO leaderboard.

        Returns:
            List of tuples: (player_id, player_name, country, rank)
        """
        if not self.session.is_logged_in:
            raise RuntimeError("Session not logged in. Call session.login() first.")

        players = []
        params = {'game': game_id, 'mode': mode}

        logger.info(f"Fetching top {num_players} players for game ID {game_id} (mode={mode})")
        
        try:
            # Paginate 10 players at a time (BGA's default page size)
            for start in range(0, num_players, 10):
                params['start'] = start
                
                logger.debug(f"Fetching players {start}-{start+9}")
                resp = self.session.get(f'{self.session.BASE_URL}{self.RANKING_URL}', params=params)
                resp.raise_for_status()
                
                data = resp.json()
                
                if 'data' not in data or 'ranks' not in data['data']:
                    logger.warning(f"Unexpected response format at start={start}")
                    break
                
                ranks_data = data['data']['ranks']
                if not ranks_data:
                    logger.info(f"No more players found at start={start}")
                    break
                
                for player in ranks_data:
                    if len(players) >= num_players:
                        break
                    
                    try:
                        player_id = int(player['id'])
                        player_name = player['name']
                        country = player['country']['name'] if player.get('country') else 'Unknown'
                        arena_rank = int(player['rank_no'])
                        
                        players.append((player_id, player_name, country, arena_rank))
                        
                    except (KeyError, ValueError, TypeError) as e:
                        logger.warning(f"Error parsing player data: {e}, player: {player}")
                        continue
                
                # If we got fewer than 10 players, we've reached the end
                if len(ranks_data) < 10:
                    break
            
            logger.info(f"Successfully fetched {len(players)} players")
            return players
            
        except Exception as e:
            logger.error(f"Error fetching leaderboard data: {e}")
            raise
    
    def get_player_details(self, player_id: int) -> Optional[dict]:
        """
        Get detailed information for a specific player
        
        Args:
            player_id: BGA player ID
            
        Returns:
            Player details dictionary or None if not found
        """
        # This could be extended to fetch more detailed player info
        # For now, we'll just return basic info from the leaderboard
        pass
