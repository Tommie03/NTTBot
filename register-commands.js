require('dotenv').config();
const { REST, Routes } = require('discord.js'); // Import REST and Routes from discord.js

// Retrieve environment variables
const clientId = process.env.CLIENT_ID;
const token = process.env.TOKEN;

// Define the commands to be registered
const commands = [
  {
    name: 'teams',
    description: 'Haal de lijst van Salamanders teams op met poules.',
    options: [
      {
        name: 'type_team',
        type: 3,  // STRING type
        description: 'Type teams om op te halen (alle, regulier, duo)',
        required: false,
        choices: [
          {
            name: 'Alle',
            value: 'alle',
          },
          {
            name: 'Regulier',
            value: 'regulier',
          },
          {
            name: 'Duo',
            value: 'duo',
          },
        ],
      },
      {
        name: 'categorie',
        type: 3,  // STRING type
        description: 'Leeftijdscategorie van teams om op te halen (alle, senior, jeugd)',
        required: false,
        choices: [
          {
            name: 'Alle',
            value: 'alle',
          },
          {
            name: 'Senior',
            value: 'senior',
          },
          {
            name: 'Jeugd',
            value: 'jeugd',
          },
        ],
      },
    ],
  },
  {
    name: 'spelers',
    description: 'Haal de lijst van spelers voor een team op.',
    options: [
      {
        name: 'team_id',
        type: 3,  // STRING type
        description: 'Het team ID',
        required: true,
      }
    ],
  },
  {
    name: 'poule',
    description: 'Haal poule informatie op via ID.',
    options: [
      {
        name: 'poule_id',
        type: 3,  // STRING type
        description: 'Het poule ID',
        required: true,
      }
    ],
  },
  {
    name: 'wedstrijden_vandaag',
    description: 'Haal de wedstrijden van vandaag op.',
  }
];

// Create a new REST instance and set the token
const rest = new REST({ version: '10' }).setToken(token);

(async () => {
  try {
    console.log('Begonnen met het vernieuwen van de applicatie (global) (/) commando\'s.');

    // Register the commands globally
    await rest.put(
      Routes.applicationCommands(clientId), 
      { body: commands }
    );

    console.log('Succesvol de applicatie (global) (/) commando\'s vernieuwd.');
  } catch (error) {
    console.error('Fout bij het vernieuwen van de applicatie (global) (/) commando\'s:', error);
  }
})();