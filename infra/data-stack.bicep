targetScope = 'subscription'

@description('Resource group dedicated to shared tripplanner data.')
param dataResourceGroupName string = 'rg-tripplanner-data'

@description('Azure region for the shared data plane.')
param location string = 'eastus2'

@description('Globally unique Cosmos DB account name.')
param cosmosAccountName string = toLower('tripplanner-data-${uniqueString(subscription().id)}')

resource dataResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: dataResourceGroupName
  location: location
}

module data './data.bicep' = {
  scope: dataResourceGroup
  params: {
    cosmosAccountName: cosmosAccountName
    location: location
  }
}

output dataResourceGroupName string = dataResourceGroup.name
output cosmosAccountName string = data.outputs.cosmosAccountName
output cosmosEndpoint string = data.outputs.cosmosEndpoint
output databaseNames array = data.outputs.databaseNames
