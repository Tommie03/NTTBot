import os
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import discord
from discord.ext import tasks, commands
import logging

from bot import APIClient
from announcements import AnnouncementBuilder

load_dotenv()
logger = logging.getLogger(__name__)

class ScheduledTasks(commands.Cog):
    """Scheduled announcements and tasks"""
    
    def __init__(self, bot):
        self.bot = bot
        self.announcement_channel_id = int(os.getenv('ANNOUNCEMENT_CHANNEL_ID', 0))
        
        # Start tasks
        if self.announcement_channel_id:
            self.daily_matches.start()
            self.weekly_standings.start()
            self.tournament_reminder.start()
            logger.info("Started scheduled tasks")
        else:
            logger.warning("ANNOUNCEMENT_CHANNEL_ID not set, tasks disabled")
    
    def cog_unload(self):
        self.daily_matches.cancel()
        self.weekly_standings.cancel()
        self.tournament_reminder.cancel()
    
    def get_channel(self):
        """Get announcement channel"""
        channel = self.bot.get_channel(self.announcement_channel_id)
        if not channel:
            logger.error(f"Channel {self.announcement_channel_id} not found")
        return channel
    
    @tasks.loop(hours=24)
    async def daily_matches(self):
        """Post daily matches at 8 AM"""
        channel = self.get_channel()
        if not channel:
            return
        
        try:
            use_mock = os.getenv('USE_MOCK_DATA', 'false').lower() == 'true'
            
            if use_mock:
                from mock_api import MockAPIClient
                api_client = MockAPIClient
            else:
                api_client = APIClient
            
            async with api_client() as api:
                embed = await AnnouncementBuilder.build_daily_matches(api)
            
            if embed:
                await channel.send(embed=embed)
                logger.info("Posted daily matches announcement")
            else:
                logger.info("No matches today, skipping announcement")
                
        except Exception as e:
            logger.error(f"Error in daily_matches: {e}", exc_info=True)
    
    @daily_matches.before_loop
    async def before_daily_matches(self):
        await self.bot.wait_until_ready()
        await self._wait_until_time(hour=8, minute=0)
    
    @tasks.loop(hours=168)  # Weekly
    async def weekly_standings(self):
        """Post weekly standings on Monday at 9 AM"""
        channel = self.get_channel()
        if not channel:
            return
        
        try:
            use_mock = os.getenv('USE_MOCK_DATA', 'false').lower() == 'true'
            
            if use_mock:
                from mock_api import MockAPIClient
                api_client = MockAPIClient
            else:
                api_client = APIClient
            
            async with api_client() as api:
                embed = await AnnouncementBuilder.build_weekly_standings(api)
            
            if embed:
                await channel.send("**Weekoverzicht**", embed=embed)
                logger.info("Posted weekly standings")
                
        except Exception as e:
            logger.error(f"Error in weekly_standings: {e}", exc_info=True)
    
    @weekly_standings.before_loop
    async def before_weekly_standings(self):
        await self.bot.wait_until_ready()
        await self._wait_until_weekday(weekday=0, hour=9, minute=0)  # Monday
    
    @tasks.loop(hours=24)
    async def tournament_reminder(self):
        """Post tournament reminder at 10 AM"""
        channel = self.get_channel()
        if not channel:
            return
        
        try:
            embed = await AnnouncementBuilder.build_tournament_reminder()
            
            if embed:
                await channel.send(embed=embed)
                logger.info("Posted tournament reminder")
                
        except Exception as e:
            logger.error(f"Error in tournament_reminder: {e}", exc_info=True)
    
    @tournament_reminder.before_loop
    async def before_tournament_reminder(self):
        await self.bot.wait_until_ready()
        await self._wait_until_time(hour=10, minute=0)
    
    async def _wait_until_time(self, hour, minute):
        """Wait until specific time today or tomorrow"""
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if now >= target:
            target += timedelta(days=1)
        
        wait_seconds = (target - now).total_seconds()
        logger.info(f"Waiting {wait_seconds/3600:.1f} hours until {target}")
        await asyncio.sleep(wait_seconds)
    
    async def _wait_until_weekday(self, weekday, hour, minute):
        """Wait until specific weekday and time (0=Monday, 6=Sunday)"""
        now = datetime.now()
        days_ahead = weekday - now.weekday()
        
        if days_ahead < 0 or (days_ahead == 0 and now.hour >= hour):
            days_ahead += 7
        
        target = now + timedelta(days=days_ahead)
        target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        wait_seconds = (target - now).total_seconds()
        logger.info(f"Waiting {wait_seconds/3600:.1f} hours until {target.strftime('%A %H:%M')}")
        await asyncio.sleep(wait_seconds)

async def setup(bot):
    await bot.add_cog(ScheduledTasks(bot))