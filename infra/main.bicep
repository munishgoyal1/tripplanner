// Trip Planner — global hosting on cheapest Azure footprint.
//
// Provisioned resources:
//   1. Log Analytics workspace (required by Container Apps)
//   2. Cosmos DB account (NoSQL API, Free Tier ON, single region)
//   3. Cosmos database + 3 containers (users, trips, audit_events) partitioned by /user_id
//   4. Container Apps managed environment (Consumption plan)
//   5. Container App with public ingress on port 8000 (FastAPI serves the SPA)
//
// Cost-keepers:
//   - Cosmos Free Tier: first 1000 RU/s + 25 GB free per subscription, forever
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
param azureOpenAiApiVersion string = '2024-12-01-preview'

@secure()
@description('Azure OpenAI API key.')
param azureOpenAiApiKey string

@secure()
@description('Duffel test or live API token.')
param duffelApiKey string

@secure()
@description('Google Places (New) API key.')
param googlePlacesApiKey string = ''

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

@description('Enable Cosmos Free Tier (only one per subscription).')
param enableCosmosFreeTier bool = true

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

var suffix = uniqueString(resourceGroup().id)
var logsName = '${namePrefix}-logs-${suffix}'
var envName = '${namePrefix}-env-${suffix}'
var appName = '${namePrefix}-app-${suffix}'
var cosmosAccountName = toLower('${namePrefix}-cosmos-${suffix}')
var cosmosDatabaseName = 'tripplanner'

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

var baseSecrets = [
  { name: 'azure-openai-api-key', value: azureOpenAiApiKey }
  { name: 'duffel-api-key', value: duffelApiKey }
  { name: 'google-places-api-key', value: googlePlacesApiKey }
  { name: 'tavily-api-key', value: tavilyApiKey }
  { name: 'cosmos-key', value: cosmos.listKeys().primaryMasterKey }
]

var baseEnv = [
  { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
  { name: 'AZURE_OPENAI_DEPLOYMENT', value: azureOpenAiDeployment }
  { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }
  { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
  { name: 'DUFFEL_API_KEY', secretRef: 'duffel-api-key' }
  { name: 'GOOGLE_PLACES_API_KEY', secretRef: 'google-places-api-key' }
  { name: 'TAVILY_API_KEY', secretRef: 'tavily-api-key' }
  { name: 'COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
  { name: 'COSMOS_KEY', secretRef: 'cosmos-key' }
  { name: 'COSMOS_DATABASE', value: cosmosDatabaseName }
  // Structured JSON logs to stdout -> Container Apps Log Analytics -> KQL.
  { name: 'LOG_JSON', value: '1' }
  // Whether to also persist raw user-message content to the restricted
  // audit_events Cosmos container. Off by default.
  { name: 'AUDIT_USER_MESSAGES', value: auditUserMessages ? '1' : '' }
]

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

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: cosmosAccountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: enableCosmosFreeTier
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

// Database carries shared throughput so both containers fit inside the free 1000 RU/s.
resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmos
  name: cosmosDatabaseName
  properties: {
    resource: {
      id: cosmosDatabaseName
    }
    options: {
      throughput: 1000
    }
  }
}

resource usersContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDb
  name: 'users'
  properties: {
    resource: {
      id: 'users'
      partitionKey: {
        paths: [
          '/user_id'
        ]
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
      }
    }
  }
}

resource tripsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDb
  name: 'trips'
  properties: {
    resource: {
      id: 'trips'
      partitionKey: {
        paths: [
          '/user_id'
        ]
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
      }
    }
  }
}

// Restricted audit sink for raw user-message content + identity events.
// PII auto-expires after 90 days (defaultTtl 7,776,000 s).
resource auditContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDb
  name: 'audit_events'
  properties: {
    resource: {
      id: 'audit_events'
      partitionKey: {
        paths: [
          '/user_id'
        ]
        kind: 'Hash'
      }
      defaultTtl: 7776000
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
      }
    }
  }
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
        traffic: [
          {
            weight: 100
            latestRevision: true
          }
        ]
      }
      secrets: concat(baseSecrets, oauthSecrets)
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
          env: concat(baseEnv, oauthEnv)
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output containerAppFqdn string = app.properties.configuration.ingress.fqdn
output containerAppUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output cosmosAccountName string = cosmos.name
output logAnalyticsId string = logs.id

