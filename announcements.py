import logging
from datetime import datetime, timezone
import discord
from bot import APIClient
from tournament_adapter import TournamentClient

logger = logging.getLogger(__name__)

class AnnouncementBuilder:
    """Builds announcement embeds"""
    
    @staticmethod
    async def build_daily_matches(api_client):
        """Build today's matches announcement"""
        try:
            matches = await api_client.get_todays_matches()
            
            if not matches:
                return None
            
            embed = discord.Embed(
                title=f"Wedstrijden Vandaag",
                description=f"{len(matches)} wedstrijden gepland",
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Group by time
            by_time = {}
            for match in matches:
                if match.tijd not in by_time:
                    by_time[match.tijd] = []
                by_time[match.tijd].append(match)
            
            # Add fields sorted by time
            for time in sorted(by_time.keys()):
                match_list = by_time[time]
                matches_text = "\n".join([f"{m.thuis} vs {m.uit}" for m in match_list])
                embed.add_field(name=f"{time}", value=matches_text, inline=False)
            
            embed.set_footer(text="Veel succes aan alle teams!")
            return embed
            
        except Exception as e:
            logger.error(f"Error building daily matches: {e}")
            return None
    
    @staticmethod
    async def build_no_matches_today():
        """Build 'no matches today' message"""
        embed = discord.Embed(
            title="📅 Geen wedstrijden vandaag",
            description="Vandaag staan er geen wedstrijden gepland.",
            color=0x808080,
            timestamp=datetime.now(timezone.utc)
        )       
        embed.set_footer(text="Gebruik /wedstrijden_vandaag om te controleren")
        return embed
    
    @staticmethod
    async def build_weekly_standings(api_client):
        """Build weekly standings for all teams"""
        try:
            teams = await api_client.get_teams()
        
            embed = discord.Embed(
                title="📊 Weekoverzicht - Team Standen",
                description="Huidige posities van onze teams",
                color=0x0099ff,
                timestamp=datetime.now(timezone.utc)
            )
        
            found_teams = 0
            for team in teams[:10]:
                try:
                    poule_teams = await api_client.get_poule(team.pID)
                
                    # Find our team and get its position
                    for idx, poule_team in enumerate(poule_teams):
                        if "salamanders" in poule_team.name.lower():
                            position = idx + 1  # Array index + 1 = position
                            embed.add_field(
                                name=f"Team {team.teamnr} - {team.group_name}",
                                value=f"**Positie:** {position}\n**Punten:** {poule_team.stand}\n**Gespeeld:** {poule_team.numm}",
                                inline=True
                            )
                            found_teams += 1
                            break
                
                    if found_teams >= 6:
                        break
                    
                except Exception as e:
                    logger.warning(f"Could not get poule for team {team.teamnr}: {e}")
                    continue
        
            if found_teams == 0:
                return None
        
            embed.set_footer(text="Gepost elke maandag • Gebruik /teams voor meer info")
            return embed
        
        except Exception as e:
            logger.error(f"Error building weekly standings: {e}")
            return None
    
    @staticmethod
    async def build_tournament_reminder():
        """Build tournament reminder"""
        try:
            async with TournamentClient() as client:
                upcoming = await client.get_upcoming_tournaments(7)
            
            if not upcoming:
                return None
            
            embed = discord.Embed(
                title="🏆 Toernooien Deze Week",
                description=f"{len(upcoming)} toernooien in de komende 7 dagen",
                color=0xffa500,
                timestamp=datetime.now(timezone.utc)
            )
            
            for t in upcoming[:5]:
                value = f"**Locatie:** {t.location}\n**Datum:** {t.date}"
                if t.registration_available:
                    value += "\n**Inschrijving:** OPEN"
                if t.tournament_url:
                    value += f"\n[Meer info]({t.tournament_url})"
                
                embed.add_field(name=t.name, value=value, inline=False)
            
            embed.set_footer(text="Gebruik /toernooien voor volledige lijst")
            return embed
            
        except Exception as e:
            logger.error(f"Error building tournament reminder: {e}")
            return None