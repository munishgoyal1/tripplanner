targetScope = 'subscription'

// The local provider cache. Canary and production deliberately do not get one:
// their .bicepparam leave cacheRedisEnabled false, so main.bicep keeps them on
// the in-memory fallback. This template exists so the instance the owner
// created by hand is described somewhere instead of only living in the portal.

@description('Resource group holding owner-only local development resources.')
param localResourceGroupName string = 'rg-tripplanner-local'

@description('Azure region for the local resource group.')
param location string = 'eastus2'

@description('Azure Managed Redis instance backing the local provider cache.')
param redisName string = 'tripplanner-local-redis-westus2-01'

@description('Region for the Redis instance. Kept separate: Balanced_B0 is not offered in every region.')
param redisLocation string = 'westus2'

@description('Azure Managed Redis SKU. Balanced_B0 is the smallest, and this cache is a single-developer convenience.')
param redisSku string = 'Balanced_B0'

resource localResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: localResourceGroupName
  location: location
}

module redis './local-redis.bicep' = {
  scope: localResourceGroup
  params: {
    redisName: redisName
    location: redisLocation
    skuName: redisSku
  }
}

output localResourceGroupName string = localResourceGroup.name
output redisName string = redis.outputs.redisName
output redisHostName string = redis.outputs.redisHostName
output redisPort int = redis.outputs.redisPort
