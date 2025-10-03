import asyncio
import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class Tournament:
    """Tournament data class"""
    id: str
    name: str
    location: str
    date: str
    start_date: str
    end_date: Optional[str]
    categories: List[str]
    registration_available: bool
    registration_url: Optional[str]
    registration_deadline: Optional[str]
    tournament_url: Optional[str]
    source: str

class TournamentClient:
    """Async wrapper for tournament database access"""
    
    def __init__(self, db_path: str = 'tournaments.db'):
        self.db_path = db_path
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Check if database exists and has data"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tournaments WHERE is_active = 1")
            count = cursor.fetchone()[0]
            conn.close()
            logger.info(f"Tournament database has {count} active tournaments")
        except Exception as e:
            logger.warning(f"Tournament database not accessible: {e}")
            logger.info("Run 'python nttbscrape.py --mode scrape' to populate tournament data")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    async def get_all_tournaments(self) -> List[Tournament]:
        """Get all active tournaments"""
        return await asyncio.to_thread(self._get_all_tournaments_sync)
    
    def _get_all_tournaments_sync(self) -> List[Tournament]:
        """Synchronous method to get all tournaments"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, name, location, date, start_date, end_date,
                       categories, registration_available, registration_url,
                       registration_deadline, tournament_url, source
                FROM tournaments 
                WHERE is_active = 1 
                ORDER BY start_date ASC
            ''')
            
            tournaments = []
            for row in cursor.fetchall():
                categories = json.loads(row[6]) if row[6] else []
                tournaments.append(Tournament(
                    id=row[0],
                    name=row[1],
                    location=row[2] or "Unknown",
                    date=row[3] or "TBA",
                    start_date=row[4] or "",
                    end_date=row[5],
                    categories=categories,
                    registration_available=bool(row[7]),
                    registration_url=row[8],
                    registration_deadline=row[9],
                    tournament_url=row[10],
                    source=row[11] or "unknown"
                ))
            
            conn.close()
            logger.info(f"Retrieved {len(tournaments)} tournaments from database")
            return tournaments
            
        except sqlite3.OperationalError as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error retrieving tournaments: {e}")
            return []
    
    async def get_upcoming_tournaments(self, days: int = 30) -> List[Tournament]:
        """Get tournaments in the next N days"""
        all_tournaments = await self.get_all_tournaments()
        
        now = datetime.now()
        cutoff = now + timedelta(days=days)
        
        upcoming = []
        for tournament in all_tournaments:
            if tournament.start_date:
                try:
                    start = datetime.fromisoformat(tournament.start_date.replace('Z', '+00:00'))
                    if now <= start <= cutoff:
                        upcoming.append(tournament)
                except (ValueError, AttributeError):
                    upcoming.append(tournament)
        
        logger.info(f"Found {len(upcoming)} upcoming tournaments in next {days} days")
        return upcoming
    
    async def get_tournaments_with_registration(self) -> List[Tournament]:
        """Get tournaments that have open registration"""
        all_tournaments = await self.get_all_tournaments()
        return [t for t in all_tournaments if t.registration_available]
    
    async def search_tournaments(self, query: str) -> List[Tournament]:
        """Search tournaments by name or location"""
        all_tournaments = await self.get_all_tournaments()
        query_lower = query.lower()
        
        results = [
            t for t in all_tournaments
            if query_lower in t.name.lower() or query_lower in t.location.lower()
        ]
        
        logger.info(f"Found {len(results)} tournaments matching '{query}'")
        return results
    
    async def get_tournament_stats(self) -> Dict[str, int]:
        """Get statistics about tournaments"""
        all_tournaments = await self.get_all_tournaments()
        upcoming = await self.get_upcoming_tournaments(30)
        with_registration = await self.get_tournaments_with_registration()
        
        return {
            'total': len(all_tournaments),
            'upcoming_30_days': len(upcoming),
            'with_registration': len(with_registration)
        }