targetScope = 'resourceGroup'

@description('Globally unique Cosmos DB account name.')
param cosmosAccountName string = toLower('tripplanner-data-${uniqueString(subscription().id)}')

@description('Azure region for the shared data plane.')
param location string = resourceGroup().location

// Throughput is DERIVED, not chosen here: scripts/derive_limits.py sizes it from
// COST_CEILING_INR_HOURLY and CHAT_MAX_CONCURRENT_GLOBAL and writes it to
// infra/billing-guardrails.json. Reading it back keeps the provisioned database
// in step with the budget that is supposed to bound it -- the same contract the
// GCP quota preferences in that file already follow.
var cosmosConfig = loadJsonContent('billing-guardrails.json').azure.cosmos

module cosmosData './modules/cosmos-data.bicep' = {
  params: {
    accountName: cosmosAccountName
    location: location
    databaseNames: [
      'tripplanner-canary'
      'tripplanner-prod'
    ]
    databaseThroughputs: [
      cosmosConfig.canary.ruPerSecond
      cosmosConfig.prod.ruPerSecond
    ]
  }
}

output cosmosAccountName string = cosmosData.outputs.accountName
output cosmosEndpoint string = cosmosData.outputs.endpoint
output databaseNames array = cosmosData.outputs.databaseNames
