using './main.bicep'

param namePrefix = 'multiagent'

// Image starts as a public hello-world; updated to ghcr.io/<owner>/multiagent
// after the first docker push (see infra/README.md for the build & push flow).
param containerImage = readEnvironmentVariable('CONTAINER_IMAGE', 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest')

// Azure OpenAI — already provisioned out of band (resource aoai-multiagent-mugoy).
param azureOpenAiEndpoint = readEnvironmentVariable('AZURE_OPENAI_ENDPOINT', '')
param azureOpenAiDeployment = readEnvironmentVariable('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o')
param azureOpenAiApiVersion = readEnvironmentVariable('AZURE_OPENAI_API_VERSION', '2024-12-01-preview')
param azureOpenAiApiKey = readEnvironmentVariable('AZURE_OPENAI_API_KEY', '')

param duffelApiKey = readEnvironmentVariable('DUFFEL_API_KEY', '')
param googlePlacesApiKey = readEnvironmentVariable('GOOGLE_PLACES_API_KEY', '')
param tavilyApiKey = readEnvironmentVariable('TAVILY_API_KEY', '')

param enableCosmosFreeTier = true
param minReplicas = 0
param maxReplicas = 1
