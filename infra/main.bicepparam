using './main.bicep'

param namePrefix = 'tripplanner'

// Image starts as a public hello-world; updated to ghcr.io/<owner>/tripplanner
// after the first docker push (see infra/README.md for the build & push flow).
param containerImage = readEnvironmentVariable('CONTAINER_IMAGE', 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest')

// Azure OpenAI — provide from .env (or generate via infra/provision-aoai.ps1).
param azureOpenAiEndpoint = readEnvironmentVariable('AZURE_OPENAI_ENDPOINT', '')
param azureOpenAiDeployment = readEnvironmentVariable('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o')
param azureOpenAiApiVersion = readEnvironmentVariable('AZURE_OPENAI_API_VERSION', '2024-10-21')
param azureOpenAiApiKey = readEnvironmentVariable('AZURE_OPENAI_API_KEY', '')

param duffelApiKey = readEnvironmentVariable('DUFFEL_API_KEY', '')
param googlePlacesApiKey = readEnvironmentVariable('GOOGLE_PLACES_API_KEY', '')
param googleMapsBrowserKey = readEnvironmentVariable('GOOGLE_MAPS_BROWSER_KEY', '')
param tavilyApiKey = readEnvironmentVariable('TAVILY_API_KEY', '')

// OAuth (all optional). Leaving WEB_SESSION_SECRET unset disables login
// flows entirely — the app stays usable with ephemeral per-session identity.
param googleOauthClientId = readEnvironmentVariable('OAUTH_GOOGLE_CLIENT_ID', '')
param googleOauthClientSecret = readEnvironmentVariable('OAUTH_GOOGLE_CLIENT_SECRET', '')
param githubOauthClientId = readEnvironmentVariable('OAUTH_GITHUB_CLIENT_ID', '')
param githubOauthClientSecret = readEnvironmentVariable('OAUTH_GITHUB_CLIENT_SECRET', '')
param webSessionSecret = readEnvironmentVariable('WEB_SESSION_SECRET', readEnvironmentVariable('CHAINLIT_AUTH_SECRET', ''))
param oauthRedirectBase = readEnvironmentVariable('OAUTH_REDIRECT_BASE', '')

param enableCosmosFreeTier = true
param minReplicas = 0
param maxReplicas = 1
