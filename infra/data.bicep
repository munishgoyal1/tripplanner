targetScope = 'resourceGroup'

@description('Globally unique Cosmos DB account name.')
param cosmosAccountName string = toLower('tripplanner-data-${uniqueString(subscription().id)}')

@description('Azure region for the shared data plane.')
param location string = resourceGroup().location

module cosmosData './modules/cosmos-data.bicep' = {
  params: {
    accountName: cosmosAccountName
    location: location
    databaseNames: [
      'tripplanner-local'
      'tripplanner-canary'
      'tripplanner-prod'
    ]
    databaseThroughput: 400
  }
}

output cosmosAccountName string = cosmosData.outputs.accountName
output cosmosEndpoint string = cosmosData.outputs.endpoint
output databaseNames array = cosmosData.outputs.databaseNames
