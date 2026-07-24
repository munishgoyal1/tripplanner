using './data-stack.bicep'

param dataResourceGroupName = readEnvironmentVariable('COSMOS_RESOURCE_GROUP', 'rg-tripplanner-data')
param location = readEnvironmentVariable('AZURE_LOCATION', 'eastus2')
