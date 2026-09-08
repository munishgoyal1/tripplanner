using './main.bicep'

param namePrefix = 'canary'
param containerImage = 'ghcr.io/munishgoyal1/tripplanner:latest'
param azureOpenAiEndpoint = readEnvironmentVariable('AZURE_OPENAI_ENDPOINT', '')
param azureOpenAiDeployment = readEnvironmentVariable('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o')
param azureOpenAiApiVersion = readEnvironmentVariable('AZURE_OPENAI_API_VERSION', '2024-10-21')
param azureOpenAiApiKey = readEnvironmentVariable('AZURE_OPENAI_API_KEY', '')
param duffelApiKey = readEnvironmentVariable('DUFFEL_API_KEY', '')
param liteapiApiKey = readEnvironmentVariable('LITEAPI_API_KEY', '')
param liteapiBaseUrl = readEnvironmentVariable('LITEAPI_BASE_URL', 'https://api.liteapi.travel/v3.0')
param travelHotelProvider = readEnvironmentVariable('TRAVEL_HOTEL_PROVIDER', 'auto')
param travelFlightProvider = readEnvironmentVariable('TRAVEL_FLIGHT_PROVIDER', 'auto')
param viatorApiKey = readEnvironmentVariable('VIATOR_API_KEY', '')
param viatorBaseUrl = readEnvironmentVariable('VIATOR_BASE_URL', 'https://api.sandbox.viator.com/partner')
param travelActivityProvider = readEnvironmentVariable('TRAVEL_ACTIVITY_PROVIDER', 'auto')
param openRouteServiceApiKey = readEnvironmentVariable('OPENROUTESERVICE_API_KEY', '')
param openRouteServiceBaseUrl = readEnvironmentVariable('OPENROUTESERVICE_BASE_URL', 'https://api.openrouteservice.org')
param openRouteServiceRouteTtlSec = int(readEnvironmentVariable('OPENROUTESERVICE_ROUTE_TTL_SEC', '21600'))
param cacheTtlSettings = {
	scale: readEnvironmentVariable('CACHE_TTL_SCALE', '1')
	stableForever: readEnvironmentVariable('CACHE_STABLE_FOREVER', '0') == '1'
	volatileForever: readEnvironmentVariable('CACHE_VOLATILE_FOREVER', '0') == '1'
	warmEverything: readEnvironmentVariable('CACHE_WARM_EVERYTHING', '0') == '1'
	hotelSearch: int(readEnvironmentVariable('HOTEL_SEARCH_CACHE_TTL_SEC', '600'))
	flightSearch: int(readEnvironmentVariable('FLIGHT_SEARCH_CACHE_TTL_SEC', '600'))
	activitySearch: int(readEnvironmentVariable('ACTIVITY_SEARCH_CACHE_TTL_SEC', '21600'))
	flightFare: int(readEnvironmentVariable('FLIGHT_CACHE_TTL_SEC', '14400'))
	hotelFare: int(readEnvironmentVariable('HOTEL_CACHE_TTL_SEC', '14400'))
	trainFare: int(readEnvironmentVariable('TRAIN_CACHE_TTL_SEC', '43200'))
	coachFare: int(readEnvironmentVariable('COACH_CACHE_TTL_SEC', '43200'))
	ferryFare: int(readEnvironmentVariable('FERRY_CACHE_TTL_SEC', '43200'))
	activityFare: int(readEnvironmentVariable('ACTIVITY_CACHE_TTL_SEC', '86400'))
}
param cacheRedisEnabled = readEnvironmentVariable('CACHE_REDIS_ENABLED', '0') == '1'
param cacheRedisUrl = readEnvironmentVariable('CACHE_REDIS_URL', '')
param cacheRedisNamespace = readEnvironmentVariable('CACHE_REDIS_NAMESPACE', 'tripplanner:provider-cache')
param cacheRedisConnectTimeoutSec = readEnvironmentVariable('CACHE_REDIS_CONNECT_TIMEOUT_SEC', '0.2')
param cacheRedisSocketTimeoutSec = readEnvironmentVariable('CACHE_REDIS_SOCKET_TIMEOUT_SEC', '0.2')
param enableAzureOpenAi = readEnvironmentVariable('ENABLE_AZURE_OPENAI', '0') == '1'
param enableGooglePlaces = readEnvironmentVariable('ENABLE_GOOGLE_PLACES', '0') == '1'
param enableGoogleMaps = readEnvironmentVariable('ENABLE_GOOGLE_MAPS', '0') == '1'
param googlePlacesApiKey = readEnvironmentVariable('GOOGLE_PLACES_API_KEY', '')
param googleMapsBrowserKey = readEnvironmentVariable('GOOGLE_MAPS_BROWSER_KEY', '')
param tavilyApiKey = readEnvironmentVariable('TAVILY_API_KEY', '')
param azureCommunicationConnectionString = readEnvironmentVariable('AZURE_COMMUNICATION_CONNECTION_STRING', '')
param azureCommunicationEmailSender = readEnvironmentVariable('AZURE_COMMUNICATION_EMAIL_SENDER', '')
param googleOauthClientId = readEnvironmentVariable('OAUTH_GOOGLE_CLIENT_ID', '')
param googleOauthClientSecret = readEnvironmentVariable('OAUTH_GOOGLE_CLIENT_SECRET', '')
param githubOauthClientId = readEnvironmentVariable('OAUTH_GITHUB_CLIENT_ID', '')
param githubOauthClientSecret = readEnvironmentVariable('OAUTH_GITHUB_CLIENT_SECRET', '')
param webSessionSecret = readEnvironmentVariable('WEB_SESSION_SECRET', readEnvironmentVariable('CHAINLIT_AUTH_SECRET', ''))
param oauthRedirectBase = readEnvironmentVariable('OAUTH_REDIRECT_BASE', '')
param cosmosAccountName = readEnvironmentVariable('COSMOS_ACCOUNT_NAME', '')
param cosmosResourceGroupName = readEnvironmentVariable('COSMOS_RESOURCE_GROUP', 'rg-tripplanner-data')
param cosmosDatabaseName = readEnvironmentVariable('COSMOS_DATABASE', 'tripplanner-canary')
param minReplicas = 0
param maxReplicas = 1
