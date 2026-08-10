// Trip Planner — global hosting on cheapest Azure footprint.
//
// Provisioned resources:
//   1. Log Analytics workspace (required by Container Apps)
//   2. Container Apps managed environment (Consumption plan)
//   3. Container App with public ingress on port 8000 (FastAPI serves the SPA)
//
// Cost-keepers:
//   - Cosmos lives in the shared data resource group provisioned by data.bicep
//   - Container Apps Consumption: 180k vCPU-sec + 2M requests / month free
//   - Container App scales to zero (minReplicas = 0) — no charge when idle
//   - Log Analytics PAYG, 30-day retention

@description('Prefix used for all resource names. Keep short.')
param namePrefix string = 'tripplanner'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Container image reference, e.g. ghcr.io/<owner>/tripplanner:latest')
param containerImage string

@description('Azure OpenAI endpoint (already provisioned out-of-band).')
param azureOpenAiEndpoint string

@description('Azure OpenAI deployment name.')
param azureOpenAiDeployment string = 'gpt-4o'

@description('Azure OpenAI API version.')
param azureOpenAiApiVersion string = '2024-10-21'

@secure()
@description('Azure OpenAI API key.')
param azureOpenAiApiKey string

@secure()
@description('Duffel test or live API token.')
param duffelApiKey string

@secure()
@description('Optional LiteAPI/Nuitee API key. Empty leaves hotel and flight provider integration inactive.')
param liteapiApiKey string = ''

@description('LiteAPI/Nuitee API base URL.')
param liteapiBaseUrl string = 'https://api.liteapi.travel/v3.0'

@description('Configured hotel provider selector. auto uses LiteAPI only when its key is present.')
param travelHotelProvider string = 'auto'

@description('Configured flight provider selector. auto uses LiteAPI only when its key is present.')
param travelFlightProvider string = 'auto'

@secure()
@description('Optional Viator partner API key. Empty leaves activity provider integration inactive.')
param viatorApiKey string = ''

@description('Viator partner API base URL.')
param viatorBaseUrl string = 'https://api.sandbox.viator.com/partner'

@description('Configured activity provider selector. auto uses Viator only when its key is present.')
param travelActivityProvider string = 'auto'

@secure()
@description('Optional OpenRouteService API key for coordinate-based directions fallback.')
param openRouteServiceApiKey string = ''

@description('OpenRouteService API base URL.')
param openRouteServiceBaseUrl string = 'https://api.openrouteservice.org'

@description('Coordinate route fallback cache TTL in seconds.')
param openRouteServiceRouteTtlSec int = 21600

@description('Enable Redis-backed provider cache. Off keeps in-memory-only behavior.')
param cacheRedisEnabled bool = false

@secure()
@description('Optional Redis URL (for example: rediss://:<key>@host:6380/0). Empty keeps local in-memory fallback only.')
param cacheRedisUrl string = ''

@description('Redis cache key namespace used by the provider cache layer.')
param cacheRedisNamespace string = 'tripplanner:provider-cache'

@description('Redis connect timeout in seconds.')
param cacheRedisConnectTimeoutSec string = '0.2'

@description('Redis socket timeout in seconds.')
param cacheRedisSocketTimeoutSec string = '0.2'

@secure()
@description('Google Places (New) API key.')
param googlePlacesApiKey string = ''

@secure()
@description('Google Maps browser key (referrer-restricted, Maps JavaScript API enabled). Sent to the browser to render the interactive trip map. Separate from googlePlacesApiKey.')
param googleMapsBrowserKey string = ''

@description('Public GA4 measurement id. Analytics remains disabled outside production and when this is empty.')
param googleAnalyticsMeasurementId string = ''

@secure()
@description('Tavily web-search API key.')
param tavilyApiKey string = ''

@secure()
@description('Google OAuth client id (web app). Optional; enables Sign in with Google.')
param googleOauthClientId string = ''

@secure()
@description('Google OAuth client secret. Required when googleOauthClientId is set.')
param googleOauthClientSecret string = ''

@secure()
@description('GitHub OAuth client id. Optional; enables Sign in with GitHub.')
param githubOauthClientId string = ''

@secure()
@description('GitHub OAuth client secret. Required when githubOauthClientId is set.')
param githubOauthClientSecret string = ''

@secure()
@description('Web session signing secret (random 32+ char string). REQUIRED to enable any OAuth or persistent guest cookies. Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))".')
param webSessionSecret string = ''

@description('Public HTTPS base URL the OAuth callback returns to (no trailing slash). Required when serving Sign in with Google through Container Apps ingress, which terminates TLS and forwards plain HTTP to the container, so request.base_url is http://. Example: https://tripplanner-app-xxx.region.azurecontainerapps.io')
param oauthRedirectBase string = ''

@description('Optional apex custom domain bound to the Container App.')
param apexCustomDomain string = ''

@description('Existing or desired managed certificate name for apexCustomDomain.')
param apexManagedCertificateName string = ''

@description('Optional www custom domain bound to the Container App.')
param wwwCustomDomain string = ''

@description('Existing or desired managed certificate name for wwwCustomDomain.')
param wwwManagedCertificateName string = ''

@description('Name of the existing shared Cosmos DB account.')
param cosmosAccountName string

@description('Resource group containing the shared Cosmos DB account.')
param cosmosResourceGroupName string = 'rg-tripplanner-data'

@description('Environment-specific database in the shared Cosmos DB account.')
param cosmosDatabaseName string

@description('Min container replicas. 0 = scale to zero when idle.')
@minValue(0)
@maxValue(10)
param minReplicas int = 0

@description('Max container replicas. Keep low to stay inside the free grant.')
@minValue(1)
@maxValue(10)
param maxReplicas int = 1

@description('If true, the restricted audit sink also stores the raw user message body. Opt-in for privacy; off by default.')
param auditUserMessages bool = false

@description('Create an Azure Monitor failure alert and email Action Group. Enable only in production.')
param enableFailureAlerts bool = false

@description('Email recipient for production failure alerts. Required when enableFailureAlerts is true.')
param failureAlertEmail string = ''

var suffix = uniqueString(resourceGroup().id)
var logsName = '${namePrefix}-logs-${suffix}'
var envName = '${namePrefix}-env-${suffix}'
var appName = '${namePrefix}-app-${suffix}'
var publicDemoJobName = '${namePrefix}-public-demo-refresh-${suffix}'
var failureAlertQuery = loadTextContent('queries/application-failures.kql')

// OAuth secrets are only attached when a value is supplied. Container Apps
// rejects empty-string secret values, so we conditionally build the secrets
// and env arrays from the OAuth params.
var oauthSecrets = concat(
  empty(googleOauthClientId) ? [] : [{ name: 'google-oauth-client-id', value: googleOauthClientId }],
  empty(googleOauthClientSecret) ? [] : [{ name: 'google-oauth-client-secret', value: googleOauthClientSecret }],
  empty(githubOauthClientId) ? [] : [{ name: 'github-oauth-client-id', value: githubOauthClientId }],
  empty(githubOauthClientSecret) ? [] : [{ name: 'github-oauth-client-secret', value: githubOauthClientSecret }],
  empty(webSessionSecret) ? [] : [{ name: 'web-session-secret', value: webSessionSecret }]
)

var oauthEnv = concat(
  empty(googleOauthClientId) ? [] : [{ name: 'OAUTH_GOOGLE_CLIENT_ID', secretRef: 'google-oauth-client-id' }],
  empty(googleOauthClientSecret) ? [] : [{ name: 'OAUTH_GOOGLE_CLIENT_SECRET', secretRef: 'google-oauth-client-secret' }],
  empty(githubOauthClientId) ? [] : [{ name: 'OAUTH_GITHUB_CLIENT_ID', secretRef: 'github-oauth-client-id' }],
  empty(githubOauthClientSecret) ? [] : [{ name: 'OAUTH_GITHUB_CLIENT_SECRET', secretRef: 'github-oauth-client-secret' }],
  empty(webSessionSecret) ? [] : [{ name: 'WEB_SESSION_SECRET', secretRef: 'web-session-secret' }],
  empty(oauthRedirectBase) ? [] : [{ name: 'OAUTH_REDIRECT_BASE', value: oauthRedirectBase }]
)

// Optional provider secrets are omitted entirely when a key is absent. Container
// Apps rejects empty secret values, and an absent key must keep that provider inactive.
var providerSecrets = concat(
  empty(liteapiApiKey) ? [] : [{ name: 'liteapi-api-key', value: liteapiApiKey }],
  empty(viatorApiKey) ? [] : [{ name: 'viator-api-key', value: viatorApiKey }],
  empty(openRouteServiceApiKey) ? [] : [{ name: 'openrouteservice-api-key', value: openRouteServiceApiKey }]
)

var redisSecrets = empty(cacheRedisUrl) ? [] : [{ name: 'cache-redis-url', value: cacheRedisUrl }]

var providerEnv = concat(
  empty(liteapiApiKey) ? [] : [
    { name: 'LITEAPI_API_KEY', secretRef: 'liteapi-api-key' }
    { name: 'LITEAPI_BASE_URL', value: liteapiBaseUrl }
    { name: 'TRAVEL_HOTEL_PROVIDER', value: travelHotelProvider }
    { name: 'TRAVEL_FLIGHT_PROVIDER', value: travelFlightProvider }
  ],
  empty(viatorApiKey) ? [] : [
    { name: 'VIATOR_API_KEY', secretRef: 'viator-api-key' }
    { name: 'VIATOR_BASE_URL', value: viatorBaseUrl }
    { name: 'TRAVEL_ACTIVITY_PROVIDER', value: travelActivityProvider }
  ],
  empty(openRouteServiceApiKey) ? [] : [
    { name: 'OPENROUTESERVICE_API_KEY', secretRef: 'openrouteservice-api-key' }
    { name: 'OPENROUTESERVICE_BASE_URL', value: openRouteServiceBaseUrl }
    { name: 'OPENROUTESERVICE_ROUTE_TTL_SEC', value: string(openRouteServiceRouteTtlSec) }
  ]
)

var baseSecrets = [
  { name: 'azure-openai-api-key', value: azureOpenAiApiKey }
  { name: 'duffel-api-key', value: duffelApiKey }
  { name: 'google-places-api-key', value: googlePlacesApiKey }
  { name: 'tavily-api-key', value: tavilyApiKey }
  { name: 'cosmos-key', value: cosmos.listKeys().primaryMasterKey }
]

var baseEnv = [
  { name: 'TRIPPLANNER_ENVIRONMENT', value: namePrefix }
  { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
  { name: 'AZURE_OPENAI_DEPLOYMENT', value: azureOpenAiDeployment }
  { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }
  { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
  { name: 'DUFFEL_API_KEY', secretRef: 'duffel-api-key' }
  { name: 'GOOGLE_PLACES_API_KEY', secretRef: 'google-places-api-key' }
  { name: 'TAVILY_API_KEY', secretRef: 'tavily-api-key' }
  { name: 'GOOGLE_MAPS_BROWSER_KEY', value: googleMapsBrowserKey }
  { name: 'GOOGLE_ANALYTICS_MEASUREMENT_ID', value: googleAnalyticsMeasurementId }
  { name: 'CACHE_REDIS_ENABLED', value: cacheRedisEnabled ? '1' : '0' }
  { name: 'CACHE_REDIS_NAMESPACE', value: cacheRedisNamespace }
  { name: 'CACHE_REDIS_CONNECT_TIMEOUT_SEC', value: cacheRedisConnectTimeoutSec }
  { name: 'CACHE_REDIS_SOCKET_TIMEOUT_SEC', value: cacheRedisSocketTimeoutSec }
  { name: 'COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
  { name: 'COSMOS_KEY', secretRef: 'cosmos-key' }
  { name: 'COSMOS_DATABASE', value: cosmosDatabaseName }
  // Structured JSON logs to stdout -> Container Apps Log Analytics -> KQL.
  { name: 'LOG_JSON', value: '1' }
  // Whether to also persist raw user-message content to the restricted
  // audit_events Cosmos container. Off by default.
  { name: 'AUDIT_USER_MESSAGES', value: auditUserMessages ? '1' : '' }
]

var redisEnv = empty(cacheRedisUrl)
  ? []
  : [{
      name: 'CACHE_REDIS_URL'
      secretRef: 'cache-redis-url'
    }]

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource failureAlertActions 'Microsoft.Insights/actionGroups@2023-01-01' = if (enableFailureAlerts) {
  name: '${namePrefix}-failure-alert-actions'
  location: 'global'
  properties: {
    groupShortName: 'tripfail'
    enabled: true
    emailReceivers: [
      {
        name: 'Tripplanner production owner'
        emailAddress: failureAlertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource failureAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = if (enableFailureAlerts) {
  name: '${namePrefix}-application-failures'
  location: location
  kind: 'LogAlert'
  properties: {
    displayName: 'Tripplanner production application failures'
    description: 'Alerts on PII-safe application, chat, or tool failure records.'
    severity: 1
    enabled: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    scopes: [logs.id]
    targetResourceTypes: ['Microsoft.OperationalInsights/workspaces']
    autoMitigate: true
    skipQueryValidation: false
    criteria: {
      allOf: [
        {
          query: failureAlertQuery
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [failureAlertActions.id]
      customProperties: {
        environment: namePrefix
        signal: 'application_failure'
      }
    }
  }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  scope: resourceGroup(cosmosResourceGroupName)
  name: cosmosAccountName
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource apexManagedCertificate 'Microsoft.App/managedEnvironments/managedCertificates@2024-03-01' = if (!empty(apexCustomDomain)) {
  parent: env
  name: apexManagedCertificateName
  location: location
  properties: {
    domainControlValidation: 'HTTP'
    subjectName: apexCustomDomain
  }
}

resource wwwManagedCertificate 'Microsoft.App/managedEnvironments/managedCertificates@2024-03-01' = if (!empty(wwwCustomDomain)) {
  parent: env
  name: wwwManagedCertificateName
  location: location
  properties: {
    domainControlValidation: 'CNAME'
    subjectName: wwwCustomDomain
  }
}

var customDomains = concat(
  empty(apexCustomDomain) ? [] : [{
    name: apexCustomDomain
    bindingType: 'SniEnabled'
    certificateId: apexManagedCertificate.id
  }],
  empty(wwwCustomDomain) ? [] : [{
    name: wwwCustomDomain
    bindingType: 'SniEnabled'
    certificateId: wwwManagedCertificate.id
  }]
)

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
        customDomains: customDomains
        traffic: [
          {
            weight: 100
            latestRevision: true
          }
        ]
      }
      secrets: concat(baseSecrets, oauthSecrets, providerSecrets, redisSecrets)
    }
    template: {
      containers: [
        {
          name: 'tripplanner'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(baseEnv, oauthEnv, providerEnv, redisEnv)
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

resource publicDemoRefreshJob 'Microsoft.App/jobs@2024-03-01' = {
  name: publicDemoJobName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    environmentId: env.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 900
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: '0 3 1 * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
    }
    template: {
      containers: [
        {
          name: 'public-demo-refresh'
          image: containerImage
          command: ['python']
          args: ['-m', 'tripplanner.public_demo']
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
            { name: 'COSMOS_DATABASE', value: cosmosDatabaseName }
            { name: 'COSMOS_USE_MANAGED_IDENTITY', value: '1' }
          ]
        }
      ]
    }
  }
}

module publicDemoCosmosRole 'public-demo-cosmos-role.bicep' = {
  scope: resourceGroup(cosmosResourceGroupName)
  params: {
    cosmosAccountName: cosmosAccountName
    principalId: publicDemoRefreshJob.identity.principalId
  }
}

output containerAppFqdn string = app.properties.configuration.ingress.fqdn
output containerAppUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
output containerAppName string = app.name
output publicDemoRefreshJobName string = publicDemoRefreshJob.name
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output cosmosAccountName string = cosmos.name
output logAnalyticsId string = logs.id

