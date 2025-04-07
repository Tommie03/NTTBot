require('dotenv').config();
const { Client, GatewayIntentBits, EmbedBuilder, ButtonBuilder, ActionRowBuilder } = require('discord.js');
const fetch = require('node-fetch');

// Bot token from environment variable
const token = process.env.TOKEN;

const client = new Client({
  intents: [GatewayIntentBits.Guilds],
});

client.once('ready', () => {
  console.log(`Logged in as ${client.user.tag}`);
});

client.on('interactionCreate', async (interaction) => {
  if (!interaction.isCommand()) return;

  const { commandName, options } = interaction;
  try {
    let response, data;

    switch (commandName) {
      case 'teams':
        const teamType = options.getString('type_team') || 'alle';
        const ageGroup = options.getString('categorie') || 'alle';

        response = await fetch('https://www.nttb-ranglijsten.nl/api/v1/?get_teams');
        data = await response.json();
        let teams = JSON.parse(data.teams);

        // Apply filters for team type and age group
        if (teamType === 'regulier') {
          teams = teams.filter(team => !team.group_name.includes('Duo'));
        } else if (teamType === 'duo') {
          teams = teams.filter(team => team.group_name.includes('Duo'));
        }

        if (ageGroup === 'senior') {
          teams = teams.filter(team => team.group_name.includes('Senioren'));
        } else if (ageGroup === 'jeugd') {
          teams = teams.filter(team => team.group_name.includes('Jeugd'));
        }

        if (!Array.isArray(teams)) {
          await interaction.reply('Error: Retrieved data is not an array.');
          return;
        }

        const teamPages = [];
        const filterDescription = ` (Filtered by ${teamType} and ${ageGroup})`;
        for (let i = 0; i < teams.length; i += 10) {
          const teamsChunk = teams.slice(i, i + 10);
          const embed = new EmbedBuilder()
            .setColor('#0099ff')
            .setTitle(`Teams${filterDescription}`)
            .setFooter({ text: 'Teams Overview', iconURL: 'https://example.com/icon.png' })
            .setDescription(
              teamsChunk.map(team => 
                `**Team ${team.teamnr}**\nClass: ${team.klasse}\nGroup: ${team.letter}\nID: ${team.pID}`
              ).join('\n\n')
            );

          teamPages.push(embed);
        }

        let currentPageTeam = 0;

        const prevButtonTeam = new ButtonBuilder()
          .setCustomId('prev_team')
          .setLabel('Previous')
          .setStyle(1)
          .setDisabled(true);

        const nextButtonTeam = new ButtonBuilder()
          .setCustomId('next_team')
          .setLabel('Next')
          .setStyle(1);

        const rowTeam = new ActionRowBuilder().addComponents(prevButtonTeam, nextButtonTeam);

        const teamMessage = await interaction.reply({ embeds: [teamPages[currentPageTeam]], components: [rowTeam], fetchReply: true });

        const teamButtonFilter = (buttonInteraction) => buttonInteraction.user.id === interaction.user.id;

        const teamButtonCollector = teamMessage.createMessageComponentCollector({ filter: teamButtonFilter, time: 60000 });

        teamButtonCollector.on('collect', async (buttonInteraction) => {
          if (buttonInteraction.customId === 'prev_team' && currentPageTeam > 0) {
            currentPageTeam--;
          } else if (buttonInteraction.customId === 'next_team' && currentPageTeam < teamPages.length - 1) {
            currentPageTeam++;
          }

          prevButtonTeam.setDisabled(currentPageTeam === 0);
          nextButtonTeam.setDisabled(currentPageTeam === teamPages.length - 1);

          await buttonInteraction.update({ embeds: [teamPages[currentPageTeam]], components: [rowTeam] });
        });

        teamButtonCollector.on('end', () => {
          teamMessage.edit({ components: [] });
        });

        break;

      case 'spelers':
        const teamId = options.getString('team_id');
        response = await fetch(`https://www.nttb-ranglijsten.nl/api/v1/?get_players&team=${teamId}`);
        data = await response.json();
        let players = JSON.parse(data[teamId]);

        if (!Array.isArray(players)) {
          await interaction.reply('Error: Retrieved data is not an array.');
          return;
        }

        const playerPages = [];
        for (let i = 0; i < players.length; i += 10) {
          const playersChunk = players.slice(i, i + 10);
          const embed = new EmbedBuilder()
            .setColor('#0099ff')
            .setTitle(`Players in Team ${teamId}`)
            .setFooter({ text: 'Players Overview', iconURL: 'https://example.com/icon.png' })
            .setDescription(
              playersChunk.map(player => 
                `**Name:** ${player.name}\n**BNR:** ${player.bnr}`
              ).join('\n\n')
            );

          playerPages.push(embed);
        }

        let currentPagePlayer = 0;

        const prevButtonPlayer = new ButtonBuilder()
          .setCustomId('prev_player')
          .setLabel('Previous')
          .setStyle(1)
          .setDisabled(true);

        const nextButtonPlayer = new ButtonBuilder()
          .setCustomId('next_player')
          .setLabel('Next')
          .setStyle(1);

        const rowPlayer = new ActionRowBuilder().addComponents(prevButtonPlayer, nextButtonPlayer);

        const playerMessage = await interaction.reply({ embeds: [playerPages[currentPagePlayer]], components: [rowPlayer], fetchReply: true });

        const playerButtonFilter = (buttonInteraction) => buttonInteraction.user.id === interaction.user.id;

        const playerButtonCollector = playerMessage.createMessageComponentCollector({ filter: playerButtonFilter, time: 60000 });

        playerButtonCollector.on('collect', async (buttonInteraction) => {
          if (buttonInteraction.customId === 'prev_player' && currentPagePlayer > 0) {
            currentPagePlayer--;
          } else if (buttonInteraction.customId === 'next_player' && currentPagePlayer < playerPages.length - 1) {
            currentPagePlayer++;
          }

          prevButtonPlayer.setDisabled(currentPagePlayer === 0);
          nextButtonPlayer.setDisabled(currentPagePlayer === playerPages.length - 1);

          await buttonInteraction.update({ embeds: [playerPages[currentPagePlayer]], components: [rowPlayer] });
        });

        playerButtonCollector.on('end', () => {
          playerMessage.edit({ components: [] });
        });

        break;

      case 'poule':
        const pouleId = options.getString('poule_id');
        response = await fetch(`https://www.nttb-ranglijsten.nl/api/v1/?get_poule&pID=${pouleId}`);
        data = await response.json();
        let teamsInPoule = JSON.parse(data.stand);

        if (!Array.isArray(teamsInPoule)) {
          await interaction.reply('Error: Retrieved data is not an array.');
          return;
        }

        const poulePages = [];
        for (let i = 0; i < teamsInPoule.length; i += 10) {
          const teamsChunk = teamsInPoule.slice(i, i + 10);
          const embed = new EmbedBuilder()
            .setColor('#0099ff')
            .setTitle(`Teams in Poule ${pouleId}`)
            .setFooter({ text: 'Poule Overview', iconURL: 'https://example.com/icon.png' })
            .setDescription(
              teamsChunk.map(team => 
                `**Name:** ${team.name}\n**Number:** ${team.numm}\n**Stand:** ${team.stand}\n**Team ID:** ${team.team}`
              ).join('\n\n')
            );

          poulePages.push(embed);
        }

        let currentPagePoule = 0;

        const prevButtonPoule = new ButtonBuilder()
          .setCustomId('prev_poule')
          .setLabel('Previous')
          .setStyle(1)
          .setDisabled(true);

        const nextButtonPoule = new ButtonBuilder()
          .setCustomId('next_poule')
          .setLabel('Next')
          .setStyle(1);

        const rowPoule = new ActionRowBuilder().addComponents(prevButtonPoule, nextButtonPoule);

        const pouleMessage = await interaction.reply({ embeds: [poulePages[currentPagePoule]], components: [rowPoule], fetchReply: true });

        const pouleButtonFilter = (buttonInteraction) => buttonInteraction.user.id === interaction.user.id;

        const pouleButtonCollector = pouleMessage.createMessageComponentCollector({ filter: pouleButtonFilter, time: 60000 });

        pouleButtonCollector.on('collect', async (buttonInteraction) => {
          if (buttonInteraction.customId === 'prev_poule' && currentPagePoule > 0) {
            currentPagePoule--;
          } else if (buttonInteraction.customId === 'next_poule' && currentPagePoule < poulePages.length - 1) {
            currentPagePoule++;
          }

          prevButtonPoule.setDisabled(currentPagePoule === 0);
          nextButtonPoule.setDisabled(currentPagePoule === poulePages.length - 1);

          await buttonInteraction.update({ embeds: [poulePages[currentPagePoule]], components: [rowPoule] });
        });

        pouleButtonCollector.on('end', () => {
          pouleMessage.edit({ components: [] });
        });

        break;

      case 'wedstrijden_vandaag':
        response = await fetch('https://www.nttb-ranglijsten.nl/api/v1/?get_wedstrijden_vandaag');
        data = await response.json();
        let wedstrijden = JSON.parse(data.wedstrijden);

        if (!Array.isArray(wedstrijden)) {
          await interaction.reply('Error: Retrieved data is not an array.');
          return;
        }

        const wedstrijdenPages = [];
        for (let i = 0; i < wedstrijden.length; i += 10) {
          const wedstrijdenChunk = wedstrijden.slice(i, i + 10);
          const embed = new EmbedBuilder()
            .setColor('#0099ff')
            .setTitle('Wedstrijden Vandaag')
            .setFooter({ text: 'Wedstrijden Overview', iconURL: 'https://example.com/icon.png' })
            .setDescription(
              wedstrijdenChunk.map(wedstrijd => 
                `**Tijd:** ${wedstrijd.tijd}\n**Thuis:** ${wedstrijd.thuis}\n**Uit:** ${wedstrijd.uit}`
              ).join('\n\n')
            );

          wedstrijdenPages.push(embed);
        }

        let currentPageWedstrijd = 0;

        const prevButtonWedstrijd = new ButtonBuilder()
          .setCustomId('prev_wedstrijd')
          .setLabel('Previous')
          .setStyle(1)
          .setDisabled(true);

        const nextButtonWedstrijd = new ButtonBuilder()
          .setCustomId('next_wedstrijd')
          .setLabel('Next')
          .setStyle(1);

        const rowWedstrijd = new ActionRowBuilder().addComponents(prevButtonWedstrijd, nextButtonWedstrijd);

        const wedstrijdMessage = await interaction.reply({ embeds: [wedstrijdenPages[currentPageWedstrijd]], components: [rowWedstrijd], fetchReply: true });

        const wedstrijdButtonFilter = (buttonInteraction) => buttonInteraction.user.id === interaction.user.id;

        const wedstrijdButtonCollector = wedstrijdMessage.createMessageComponentCollector({ filter: wedstrijdButtonFilter, time: 60000 });

        wedstrijdButtonCollector.on('collect', async (buttonInteraction) => {
          if (buttonInteraction.customId === 'prev_wedstrijd' && currentPageWedstrijd > 0) {
            currentPageWedstrijd--;
          } else if (buttonInteraction.customId === 'next_wedstrijd' && currentPageWedstrijd < wedstrijdenPages.length - 1) {
            currentPageWedstrijd++;
          }

          prevButtonWedstrijd.setDisabled(currentPageWedstrijd === 0);
          nextButtonWedstrijd.setDisabled(currentPageWedstrijd === wedstrijdenPages.length - 1);

          await buttonInteraction.update({ embeds: [wedstrijdenPages[currentPageWedstrijd]], components: [rowWedstrijd] });
        });

        wedstrijdButtonCollector.on('end', () => {
          wedstrijdMessage.edit({ components: [] });
        });

        break;

      default:
        await interaction.reply('Unknown command!');
    }

  } catch (error) {
    console.error(error);
    await interaction.reply('There was an error processing this command.');
  }
});

client.login(token);
