import os
import asyncio
import aiohttp
import json
import re
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta, timezone
import logging
from dataclasses import dataclass
from dotenv import load_dotenv

import discord
from discord.ext import commands, tasks
from discord import app_commands

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import tournament adapter
try:
    from tournament_adapter import TournamentClient, Tournament
    TOURNAMENTS_AVAILABLE = True
    logger.info("Tournament features enabled")
except ImportError:
    TOURNAMENTS_AVAILABLE = False
    logger.warning("Tournament adapter not found - tournament commands will be disabled")

# NTTB Styling
class NTTBStyle:
    PRIMARY_BLUE = 0x0066cc
    ACCENT_ORANGE = 0xff6600
    SUCCESS_GREEN = 0x00cc66
    NEUTRAL_GRAY = 0x808080
    
    EMOJI = {
        'ping_pong': '🏓', 'team': '👥', 'player': '👤',
        'standings': '📊', 'trophy': '🏆', 'home': '🏠',
        'away': '🚌', 'time': '⏰', 'info': 'ℹ️',
    }

@dataclass
class Team:
    teamnr: str
    klasse: str
    letter: str
    pID: str
    tID: str  # Team ID - used for getting players
    group_name: str

@dataclass
class Player:
    name: str
    bnr: str

@dataclass
class PouleTeam:
    name: str
    numm: str
    stand: str
    team: str

@dataclass
class Match:
    tijd: str
    thuis: str
    uit: str

class NTTBAPIError(Exception):
    pass

class APIClient:
    def __init__(self, base_url: str = "https://www.nttb-ranglijsten.nl/api/v1/"):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: Dict[str, Any] = {}
        self.cache_timestamps: Dict[str, datetime] = {}
        self.cache_duration = timedelta(minutes=5)
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'nl-NL,nl;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://www.nttb-ranglijsten.nl/',
                'Origin': 'https://www.nttb-ranglijsten.nl',
                'DNT': '1',
                'Connection': 'keep-alive',
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _is_cache_valid(self, key: str) -> bool:
        if key not in self.cache_timestamps:
            return False
        return datetime.now() - self.cache_timestamps[key] < self.cache_duration
    
    async def _make_request(self, endpoint: str) -> Dict[str, Any]:
        cache_key = endpoint
        
        if self._is_cache_valid(cache_key):
            logger.info(f"Returning cached data for {endpoint}")
            return self.cache[cache_key]
        
        if not self.session:
            raise NTTBAPIError("Session not initialized")
        
        url = f"{self.base_url}?{endpoint}"
        
        # Add small delay to avoid rate limiting
        await asyncio.sleep(0.5)
        
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    raise NTTBAPIError(f"API returned status {response.status}")
                
                text = await response.text()
                
                # Check if response is empty
                if not text or text.strip() == "":
                    logger.warning(f"Empty response from API for {endpoint}")
                    raise NTTBAPIError(f"Empty response from API")
                
                # Check if response is HTML error page instead of JSON
                if text.strip().startswith('<') or 'SELECT' in text[:100]:
                    logger.error(f"API returned HTML/SQL instead of JSON for {endpoint}")
                    logger.error(f"Response preview: {text[:300]}")
                    raise NTTBAPIError(f"API returned HTML error page instead of JSON")
                
                data = json.loads(text)
                
                self.cache[cache_key] = data
                self.cache_timestamps[cache_key] = datetime.now()
                
                logger.info(f"Successfully fetched and cached data for {endpoint}")
                return data
                
        except aiohttp.ClientError as e:
            logger.error(f"Network error when fetching {endpoint}: {e}")
            raise NTTBAPIError(f"Network error: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {endpoint}: {e}")
            logger.error(f"Response text (first 200 chars): {text[:200] if text else 'EMPTY'}")
            raise NTTBAPIError(f"Invalid JSON response: {e}")
    
    async def get_teams(self) -> List[Team]:
        try:
            data = await self._make_request("get_teams")
            teams_data = json.loads(data.get('teams', '[]'))
            
            return [Team(
                teamnr=team.get('teamnr', 'Unknown'),
                klasse=team.get('klasse', 'Unknown'),
                letter=team.get('letter', 'Unknown'),
                pID=team.get('pID', 'Unknown'),
                tID=team.get('tID', 'Unknown'),  # Team ID - the actual identifier for players!
                group_name=team.get('group_name', 'Unknown')
            ) for team in teams_data]
            
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing teams data: {e}")
            raise NTTBAPIError(f"Error parsing teams data: {e}")
    
    async def get_players(self, team_id: str) -> List[Player]:
        """Get players for a team using tID (Team ID), not teamnr or pID
        
        Args:
            team_id: The tID field from get_teams (e.g., "1134502")
        """
        try:
            data = await self._make_request(f"get_players&team={team_id}")
            
            # Check for API errors
            if 'error' in data and data['error'] != 'OK':
                error_msg = data.get('error', 'Unknown error')
                logger.warning(f"API returned error for team {team_id}: {error_msg}")
                return []
            
            # The API returns player data under the tID key
            players_data = []
            
            if team_id in data:
                try:
                    value = data.get(team_id, '[]')
                    # Check if it's already a list or needs parsing
                    if isinstance(value, str):
                        players_data = json.loads(value)
                    elif isinstance(value, list):
                        players_data = value
                    logger.info(f"Successfully parsed {len(players_data)} players for team {team_id}")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse players JSON for team {team_id}: {e}")
            else:
                logger.warning(f"Team {team_id} not found in API response")
            
            return [Player(
                name=player.get('name', 'Unknown'),
                bnr=player.get('bnr', 'Unknown')
            ) for player in players_data if isinstance(player, dict)]
            
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing players data for team {team_id}: {e}")
            return []
    
    async def get_poule(self, poule_id: str) -> List[PouleTeam]:
        try:
            data = await self._make_request(f"get_poule&pID={poule_id}")
            poule_data = json.loads(data.get('stand', '[]'))
            
            return [PouleTeam(
                name=team.get('name', 'Unknown'),
                numm=team.get('numm', 'Unknown'),
                stand=team.get('stand', 'Unknown'),
                team=team.get('team', 'Unknown')
            ) for team in poule_data]
            
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing poule data for {poule_id}: {e}")
            raise NTTBAPIError(f"Error parsing poule data: {e}")
    
    async def get_todays_matches(self) -> List[Match]:
        try:
            # Correct endpoint is "get_today", not "get_wedstrijden_vandaag"
            data = await self._make_request("get_today")
            
            # Check if data is a string that needs parsing
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    logger.error(f"Could not parse API response as JSON")
                    return []
            
            # Check if data is now a dict
            if not isinstance(data, dict):
                logger.error(f"Unexpected data type: {type(data)}")
                return []
            
            # The API uses "today" as the key
            if 'today' not in data:
                logger.warning(f"No 'today' key in response. Available keys: {list(data.keys())}")
                return []
            
            matches_raw = data.get('today', '[]')
            
            # Parse JSON if it's a string
            if isinstance(matches_raw, str):
                matches_data = json.loads(matches_raw)
            elif isinstance(matches_raw, list):
                matches_data = matches_raw
            else:
                logger.error(f"Unexpected today format: {type(matches_raw)}")
                return []
            
            # Create Match objects from the data
            matches = []
            for match in matches_data:
                if isinstance(match, dict):
                    # Combine date and time for display
                    tijd = f"{match.get('date', '')} {match.get('time', '')}".strip()
                    matches.append(Match(
                        tijd=tijd if tijd else 'Unknown',
                        thuis=match.get('htm', 'Unknown'),
                        uit=match.get('otm', 'Unknown')
                    ))
            
            logger.info(f"Found {len(matches)} matches for today")
            return matches
            
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing matches data: {e}", exc_info=True)
            return []

class PaginationView(discord.ui.View):
    def __init__(self, embeds: List[discord.Embed], *, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_page = 0
        self.update_buttons()
    
    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == len(self.embeds) - 1
    
    @discord.ui.button(label='◀', style=discord.ButtonStyle.blurple)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(label='▶', style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

class SalamandersBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            description="Enhanced Salamanders Table Tennis Bot"
        )
    
    async def setup_hook(self):
        logger.info("Bot is starting up...")
        await self.tree.sync()
        logger.info("Command tree synced")
    
    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        await refresh_teams_cache()
        logger.info('------')
    
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        logger.error(f"Command error: {error}")
        
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Command is on cooldown. Try again in {error.retry_after:.2f} seconds.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "An error occurred while processing your command.",
                ephemeral=True
            )

bot = SalamandersBot()

_teams_cache = []
_last_cache_update = None

async def refresh_teams_cache():
    global _teams_cache, _last_cache_update
    try:
        async with APIClient() as api:
            _teams_cache = await api.get_teams()
            _last_cache_update = datetime.now()
            logger.info(f"Cached {len(_teams_cache)} teams for autocomplete")
    except Exception as e:
        logger.error(f"Failed to cache teams: {e}")

async def team_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete for team selection - fast and cached"""
    global _teams_cache, _last_cache_update
    
    # Use cache even if slightly old to avoid timeout
    if not _teams_cache:
        return []
    
    # Refresh in background if needed (don't wait for it)
    if not _last_cache_update or (datetime.now() - _last_cache_update).seconds > 300:
        asyncio.create_task(refresh_teams_cache())
    
    current_lower = current.lower()
    filtered = [
        t for t in _teams_cache 
        if current_lower in t.teamnr.lower() or current_lower in t.group_name.lower() or current_lower in t.klasse.lower()
    ]
    
    return [
        app_commands.Choice(
            name=f"Team {t.teamnr} - {t.group_name} ({t.klasse})".replace("  ", " ")[:100],
            value=t.pID
        )
        for t in filtered[:25]
    ]

def create_embeds(items: List[Any], title: str, format_func, items_per_page: int = 10, color: int = None) -> List[discord.Embed]:
    if color is None:
        color = NTTBStyle.PRIMARY_BLUE
    
    if not items:
        embed = discord.Embed(
            title=f"{NTTBStyle.EMOJI['info']} {title}",
            description="Geen data beschikbaar",
            color=NTTBStyle.NEUTRAL_GRAY
        )
        embed.set_footer(text="TTV Salamanders")
        return [embed]
    
    embeds = []
    total_pages = (len(items) + items_per_page - 1) // items_per_page
    
    for i in range(0, len(items), items_per_page):
        chunk = items[i:i + items_per_page]
        current_page = i // items_per_page + 1
        
        embed = discord.Embed(
            title=f"{NTTBStyle.EMOJI['ping_pong']} {title}",
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        
        description_parts = [format_func(item) for item in chunk]
        embed.description = '\n\n'.join(description_parts)
        
        embed.set_footer(text=f"Pagina {current_page}/{total_pages} • TTV Salamanders")
        
        embeds.append(embed)
    
    return embeds

@bot.tree.command(name="team_info", description="Volledige team informatie")
@app_commands.describe(team="Typ om een team te zoeken")
@app_commands.autocomplete(team=team_autocomplete)
async def team_info_command(interaction: discord.Interaction, team: str):
    # Defer immediately to avoid timeout
    await interaction.response.defer()
    
    try:
        async with APIClient() as api:
            teams = await api.get_teams()
            selected_team = next((t for t in teams if t.pID == team), None)
            
            if not selected_team:
                await interaction.followup.send(f"Team niet gevonden", ephemeral=True)
                return
            
            # Get players using tID (Team ID), NOT teamnr or pID!
            players = []
            try:
                logger.info(f"Getting players for team {selected_team.teamnr} using tID: {selected_team.tID}")
                players = await api.get_players(selected_team.tID)
                if players:
                    logger.info(f"Found {len(players)} players using tID")
                else:
                    logger.warning(f"No players found for team {selected_team.teamnr}")
            except Exception as e:
                logger.error(f"Error getting players for team {selected_team.teamnr}: {e}")
            
            # Get poule standings with error handling
            poule_teams = []
            position = None
            team_data = None
            
            try:
                poule_teams = await api.get_poule(selected_team.pID)
                
                for idx, pt in enumerate(poule_teams):
                    team_lower = pt.name.lower()
                    if "salamanders" in team_lower:
                        # Use regex to match exact team number with word boundaries
                        pattern = r'\b' + re.escape(selected_team.teamnr) + r'\b'
                        if re.search(pattern, pt.name, re.IGNORECASE):
                            position = idx + 1
                            team_data = pt
                            logger.info(f"Found team position: {position} for team {selected_team.teamnr}")
                            break
            except NTTBAPIError as e:
                logger.warning(f"Could not fetch poule standings for team {selected_team.teamnr}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error getting poule for team {selected_team.teamnr}: {e}")
            
            embed = discord.Embed(
                title=f"{NTTBStyle.EMOJI['ping_pong']} Team {selected_team.teamnr}",
                description=f"**{selected_team.group_name}**",
                color=NTTBStyle.PRIMARY_BLUE,
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name=f"{NTTBStyle.EMOJI['standings']} Competitie",
                value=f"**Klasse:** {selected_team.klasse}\n**Poule:** {selected_team.letter}",
                inline=True
            )
            
            if position and team_data:
                embed.add_field(
                    name=f"{NTTBStyle.EMOJI['trophy']} Positie",
                    value=f"**{position}e plaats**\n**Punten:** {team_data.stand}\n**Gespeeld:** {team_data.numm}",
                    inline=True
                )
            
            if players:
                player_list = "\n".join([f"• {p.name}" for p in players[:8]])
                if len(players) > 8:
                    player_list += f"\n• ... en {len(players) - 8} anderen"
            else:
                player_list = "Geen spelers gevonden"
            
            embed.add_field(
                name=f"{NTTBStyle.EMOJI['team']} Spelers ({len(players)})",
                value=player_list,
                inline=False
            )
            
            embed.set_footer(text="TTV Salamanders • NTTB Competitie")
            
            await interaction.followup.send(embed=embed)
            
    except Exception as e:
        logger.error(f"Error in team_info: {e}", exc_info=True)
        await interaction.followup.send(f"Fout: {str(e)[:200]}", ephemeral=True)

@bot.tree.command(name="klassement", description="Bekijk poule klassement")
@app_commands.describe(team="Selecteer een team om hun poule te zien")
@app_commands.autocomplete(team=team_autocomplete)
async def klassement_command(interaction: discord.Interaction, team: str):
    # Defer immediately to avoid timeout
    await interaction.response.defer()
    
    try:
        async with APIClient() as api:
            teams = await api.get_teams()
            selected_team = next((t for t in teams if t.pID == team), None)
            
            if not selected_team:
                await interaction.followup.send(f"Team niet gevonden", ephemeral=True)
                return
            
            try:
                poule_teams = await api.get_poule(selected_team.pID)
            except NTTBAPIError as e:
                logger.error(f"API error getting poule for {selected_team.pID}: {e}")
                embed = discord.Embed(
                    title="❌ Fout bij ophalen klassement",
                    description=f"Kan klassement niet ophalen voor {selected_team.group_name}.\n\nDe API geeft een foutmelding. Probeer het later opnieuw.",
                    color=NTTBStyle.NEUTRAL_GRAY
                )
                embed.set_footer(text="Als dit probleem blijft bestaan, neem contact op met de beheerder")
                await interaction.followup.send(embed=embed)
                return
            
            if not poule_teams:
                embed = discord.Embed(
                    title="ℹ️ Geen Data",
                    description=f"Geen klassement beschikbaar voor {selected_team.group_name}.",
                    color=NTTBStyle.NEUTRAL_GRAY
                )
                await interaction.followup.send(embed=embed)
                return
            
            embed = discord.Embed(
                title=f"{NTTBStyle.EMOJI['standings']} Klassement - {selected_team.klasse}",
                description=f"**Poule {selected_team.letter}**\n",
                color=NTTBStyle.PRIMARY_BLUE,
                timestamp=datetime.now(timezone.utc)
            )
            
            standings_text = "```\nPos  Team                    Pnt  Ges\n" + "─" * 42 + "\n"
            
            for idx, pt in enumerate(poule_teams[:10], 1):
                team_name = pt.name[:22].ljust(22)
                is_salamanders = "salamanders" in pt.name.lower()
                marker = "►" if is_salamanders else " "
                
                standings_text += f"{marker}{idx:2d}  {team_name}  {int(pt.stand):3d}  {int(pt.numm):3d}\n"
            
            standings_text += "```"
            
            embed.description += standings_text
            embed.set_footer(text="Pnt = Punten | Ges = Gespeeld")
            
            await interaction.followup.send(embed=embed)
            
    except Exception as e:
        logger.error(f"Error in klassement: {e}", exc_info=True)
        await interaction.followup.send(f"Fout: {str(e)[:200]}", ephemeral=True)

@bot.tree.command(name="spelerinfo", description="Bekijk spelerslijst van een team")
@app_commands.describe(team="Selecteer een team")
@app_commands.autocomplete(team=team_autocomplete)
async def spelerinfo_command(interaction: discord.Interaction, team: str):
    # Defer immediately to avoid timeout
    await interaction.response.defer()
    
    try:
        async with APIClient() as api:
            teams = await api.get_teams()
            selected_team = next((t for t in teams if t.pID == team), None)
            
            if not selected_team:
                await interaction.followup.send(f"Team niet gevonden", ephemeral=True)
                return
            
            # Get players using tID (Team ID), NOT teamnr or pID!
            players = []
            try:
                logger.info(f"Getting players for team {selected_team.teamnr} using tID: {selected_team.tID}")
                players = await api.get_players(selected_team.tID)
                if players:
                    logger.info(f"Found {len(players)} players using tID")
                else:
                    logger.warning(f"No players found for team {selected_team.teamnr}")
            except Exception as e:
                logger.error(f"Error getting players for team {selected_team.teamnr}: {e}")
            
            embed = discord.Embed(
                title=f"{NTTBStyle.EMOJI['team']} Spelerslijst Team {selected_team.teamnr}",
                description=f"**{selected_team.group_name}** - {selected_team.klasse}",
                color=NTTBStyle.PRIMARY_BLUE,
                timestamp=datetime.now(timezone.utc)
            )
            
            if players:
                player_text = ""
                for i, player in enumerate(players, 1):
                    player_text += f"`{i:2d}` **{player.name}**\n     └ Bondsnummer: {player.bnr}\n"
                
                embed.add_field(name="Spelers", value=player_text, inline=False)
            else:
                embed.description += "\n\nGeen spelers gevonden voor dit team"
            
            embed.set_footer(text=f"Totaal {len(players)} spelers • TTV Salamanders")
            
            await interaction.followup.send(embed=embed)
            
    except Exception as e:
        logger.error(f"Error in spelerinfo: {e}", exc_info=True)
        await interaction.followup.send(f"Fout: {str(e)[:200]}", ephemeral=True)

@bot.tree.command(name="teams", description="Lijst van Salamanders teams met filters")
@app_commands.describe(type_team="Type teams", categorie="Leeftijdscategorie")
@app_commands.choices(type_team=[
    app_commands.Choice(name="Alle", value="alle"),
    app_commands.Choice(name="Regulier", value="regulier"),
    app_commands.Choice(name="Duo", value="duo"),
])
@app_commands.choices(categorie=[
    app_commands.Choice(name="Alle", value="alle"),
    app_commands.Choice(name="Senior", value="senior"),
    app_commands.Choice(name="Jeugd", value="jeugd"),
])
async def teams_command(interaction: discord.Interaction, type_team: str = "alle", categorie: str = "alle"):
    # Defer immediately to avoid timeout
    await interaction.response.defer()
    
    try:
        async with APIClient() as api:
            teams = await api.get_teams()
            
            if type_team == "regulier":
                teams = [t for t in teams if "Duo" not in t.group_name]
            elif type_team == "duo":
                teams = [t for t in teams if "Duo" in t.group_name]
            
            if categorie == "senior":
                teams = [t for t in teams if "Senioren" in t.group_name]
            elif categorie == "jeugd":
                teams = [t for t in teams if "Jeugd" in t.group_name]
            
            def format_team(team: Team) -> str:
                return f"**{NTTBStyle.EMOJI['team']} Team {team.teamnr}**\n└ {team.group_name}\n└ Klasse: {team.klasse}\n└ Poule: {team.letter}"
            
            title = f"Teams (Filter: {type_team}/{categorie})" if type_team != "alle" or categorie != "alle" else "Teams"
            embeds = create_embeds(teams, title, format_team)
            
            if len(embeds) == 1:
                await interaction.followup.send(embed=embeds[0])
            else:
                view = PaginationView(embeds)
                await interaction.followup.send(embed=embeds[0], view=view)
                
    except Exception as e:
        logger.error(f"Error in teams command: {e}")
        await interaction.followup.send("Er is een fout opgetreden.", ephemeral=True)

@bot.tree.command(name="wedstrijden_vandaag", description="Wedstrijden van vandaag")
async def matches_command(interaction: discord.Interaction):
    # Defer immediately to avoid timeout
    await interaction.response.defer()
    
    try:
        async with APIClient() as api:
            matches = await api.get_todays_matches()
            
            def format_match(match: Match) -> str:
                return f"**{NTTBStyle.EMOJI['time']} {match.tijd}**\n{NTTBStyle.EMOJI['home']} {match.thuis}\n{NTTBStyle.EMOJI['away']} {match.uit}"
            
            embeds = create_embeds(matches, "Wedstrijden Vandaag", format_match, color=NTTBStyle.SUCCESS_GREEN)
            
            if len(embeds) == 1:
                await interaction.followup.send(embed=embeds[0])
            else:
                view = PaginationView(embeds)
                await interaction.followup.send(embed=embeds[0], view=view)
                
    except Exception as e:
        logger.error(f"Error in matches command: {e}")
        await interaction.followup.send("Er is een fout opgetreden.", ephemeral=True)

@bot.tree.command(name="toernooien", description="Bekijk komende toernooien")
@app_commands.describe(days="Aantal dagen vooruit (standaard 30)")
async def tournaments_command(interaction: discord.Interaction, days: int = 30):
    await interaction.response.defer()
    
    if not TOURNAMENTS_AVAILABLE:
        await interaction.followup.send(
            "Toernooifunctie is niet beschikbaar. Voer eerst `python nttbscrape.py --mode scrape` uit.",
            ephemeral=True
        )
        return
    
    try:
        async with TournamentClient() as client:
            tournaments = await client.get_upcoming_tournaments(days)
        
        if not tournaments:
            embed = discord.Embed(
                title="🏆 Geen Toernooien Gevonden",
                description=f"Geen toernooien gevonden in de komende {days} dagen.",
                color=NTTBStyle.NEUTRAL_GRAY
            )
            await interaction.followup.send(embed=embed)
            return
        
        def format_tournament(t: Tournament) -> str:
            text = f"**{t.name}**\n📍 {t.location} | 📅 {t.date}"
            if t.categories:
                cats = ", ".join(t.categories[:3])
                text += f"\n🏓 {cats}"
            if t.registration_available:
                text += "\n✅ **Inschrijving open**"
            if t.tournament_url:
                text += f"\n[Meer info]({t.tournament_url})"
            return text
        
        embeds = create_embeds(
            tournaments, 
            f"Komende Toernooien ({days} dagen)",
            format_tournament,
            items_per_page=5,
            color=NTTBStyle.ACCENT_ORANGE
        )
        
        if len(embeds) == 1:
            await interaction.followup.send(embed=embeds[0])
        else:
            view = PaginationView(embeds)
            await interaction.followup.send(embed=embeds[0], view=view)
            
    except Exception as e:
        logger.error(f"Error in tournaments command: {e}", exc_info=True)
        await interaction.followup.send(
            "Fout bij ophalen toernooien. Zorg dat de database bestaat (run nttbscrape.py).",
            ephemeral=True
        )

@bot.tree.command(name="toernooi_zoeken", description="Zoek een toernooi")
@app_commands.describe(query="Zoekterm (naam of locatie)")
async def tournament_search_command(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    
    if not TOURNAMENTS_AVAILABLE:
        await interaction.followup.send(
            "Toernooifunctie is niet beschikbaar.",
            ephemeral=True
        )
        return
    
    try:
        async with TournamentClient() as client:
            tournaments = await client.search_tournaments(query)
        
        if not tournaments:
            embed = discord.Embed(
                title="🔍 Geen Resultaten",
                description=f"Geen toernooien gevonden voor '{query}'",
                color=NTTBStyle.NEUTRAL_GRAY
            )
            await interaction.followup.send(embed=embed)
            return
        
        def format_tournament(t: Tournament) -> str:
            text = f"**{t.name}**\n📍 {t.location} | 📅 {t.date}"
            if t.registration_available:
                text += "\n✅ **Inschrijving open**"
            if t.tournament_url:
                text += f"\n[Link]({t.tournament_url})"
            return text
        
        embeds = create_embeds(
            tournaments[:15],  # Limit to 15 results
            f"Zoekresultaten: '{query}'",
            format_tournament,
            items_per_page=5,
            color=NTTBStyle.ACCENT_ORANGE
        )
        
        if len(embeds) == 1:
            await interaction.followup.send(embed=embeds[0])
        else:
            view = PaginationView(embeds)
            await interaction.followup.send(embed=embeds[0], view=view)
            
    except Exception as e:
        logger.error(f"Error in tournament search: {e}", exc_info=True)
        await interaction.followup.send("Fout bij zoeken.", ephemeral=True)

@bot.tree.command(name="toernooi_stats", description="Toernooi statistieken")
async def tournament_stats_command(interaction: discord.Interaction):
    await interaction.response.defer()
    
    if not TOURNAMENTS_AVAILABLE:
        await interaction.followup.send(
            "Toernooifunctie is niet beschikbaar.",
            ephemeral=True
        )
        return
    
    try:
        async with TournamentClient() as client:
            stats = await client.get_tournament_stats()
        
        embed = discord.Embed(
            title="📊 Toernooi Statistieken",
            color=NTTBStyle.PRIMARY_BLUE,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Totaal Actief",
            value=f"**{stats['total']}** toernooien",
            inline=True
        )
        embed.add_field(
            name="Komende 30 Dagen",
            value=f"**{stats['upcoming_30_days']}** toernooien",
            inline=True
        )
        embed.add_field(
            name="Open Inschrijving",
            value=f"**{stats['with_registration']}** toernooien",
            inline=True
        )
        
        embed.set_footer(text="TTV Salamanders • NTTB Toernooien")
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in tournament stats: {e}", exc_info=True)
        await interaction.followup.send("Fout bij ophalen statistieken.", ephemeral=True)
async def help_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    embed = discord.Embed(
        title=f"{NTTBStyle.EMOJI['info']} Salamanders Bot Commando's",
        description="Volledige lijst van beschikbare commando's",
        color=NTTBStyle.PRIMARY_BLUE
    )
    
    embed.add_field(
        name=f"{NTTBStyle.EMOJI['ping_pong']} Team Commando's",
        value=(
            "`/team_info` - Volledige team informatie\n"
            "`/klassement` - Poule klassement\n"
            "`/spelerinfo` - Spelerslijst\n"
        ),
        inline=False
    )
    
    embed.add_field(
        name=f"{NTTBStyle.EMOJI['team']} Andere Commando's",
        value=(
            "`/teams` - Lijst alle teams met filters\n"
            "`/wedstrijden_vandaag` - Wedstrijden vandaag"
        ),
        inline=False
    )
    
    embed.set_footer(text="TTV Salamanders Bot")
    
    await interaction.followup.send(embed=embed, ephemeral=True)

async def load_extensions():
    """Load optional extensions like scheduled tasks"""
    if os.getenv('ENABLE_ANNOUNCEMENTS', 'false').lower() == 'true':
        try:
            # Check if required environment variables are set
            if not os.getenv('ANNOUNCEMENT_CHANNEL_ID'):
                logger.warning("ENABLE_ANNOUNCEMENTS is true but ANNOUNCEMENT_CHANNEL_ID not set")
                return
            
            await bot.load_extension('scheduled_tasks')
            logger.info("Loaded scheduled announcements extension")
        except Exception as e:
            logger.error(f"Failed to load scheduled tasks: {e}")
            logger.info("Make sure scheduled_tasks.py and announcements.py exist in the same directory")

if __name__ == "__main__":
    token = os.getenv('TOKEN')
    if not token:
        logger.error("No token found in environment variables")
        exit(1)
    
    logger.info("Starting Salamanders Bot...")
    
    async def main():
        async with bot:
            await load_extensions()
            await bot.start(token)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except discord.LoginFailure:
        logger.error("Invalid token provided")
    except Exception as e:
        logger.error(f"Error starting bot: {e}")