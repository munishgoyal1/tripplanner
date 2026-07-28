using './main.bicep'

param namePrefix = 'canary'
param containerImage = 'ghcr.io/munishgoyal1/tripplanner:latest'
param azureOpenAiEndpoint = 'https://aoaicanarymd1ks-2703a.openai.azure.com/'
param azureOpenAiDeployment = 'gpt-4-1-canary'
param azureOpenAiApiVersion = '2024-10-21'
param azureOpenAiApiKey = readEnvironmentVariable('AZURE_OPENAI_API_KEY', '')
param duffelApiKey = readEnvironmentVariable('DUFFEL_API_KEY', '')
param googlePlacesApiKey = readEnvironmentVariable('GOOGLE_PLACES_API_KEY', '')
param googleMapsBrowserKey = readEnvironmentVariable('GOOGLE_MAPS_BROWSER_KEY', '')
param tavilyApiKey = readEnvironmentVariable('TAVILY_API_KEY', '')
param googleOauthClientId = readEnvironmentVariable('OAUTH_GOOGLE_CLIENT_ID', '')
param googleOauthClientSecret = readEnvironmentVariable('OAUTH_GOOGLE_CLIENT_SECRET', '')
param githubOauthClientId = readEnvironmentVariable('OAUTH_GITHUB_CLIENT_ID', '')
param githubOauthClientSecret = readEnvironmentVariable('OAUTH_GITHUB_CLIENT_SECRET', '')
param webSessionSecret = readEnvironmentVariable('WEB_SESSION_SECRET', readEnvironmentVariable('CHAINLIT_AUTH_SECRET', ''))
param oauthRedirectBase = ''
param cosmosAccountName = readEnvironmentVariable('COSMOS_ACCOUNT_NAME', '')
param cosmosResourceGroupName = readEnvironmentVariable('COSMOS_RESOURCE_GROUP', 'rg-tripplanner-data')
param cosmosDatabaseName = 'tripplanner-canary'
param minReplicas = 0
param maxReplicas = 1
