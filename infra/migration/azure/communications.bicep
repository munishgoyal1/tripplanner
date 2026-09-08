targetScope = 'resourceGroup'

@description('Globally unique Azure Communication Services name.')
param communicationServiceName string

@description('Globally unique Azure Email Communication Service name.')
param emailServiceName string

@description('Azure data location for Communication Services.')
param dataLocation string = 'United States'

resource email 'Microsoft.Communication/emailServices@2023-04-01' = {
  name: emailServiceName
  location: 'global'
  properties: {
    dataLocation: dataLocation
  }
}

resource domain 'Microsoft.Communication/emailServices/domains@2023-04-01' = {
  parent: email
  name: 'AzureManagedDomain'
  location: 'global'
  properties: {
    domainManagement: 'AzureManaged'
    userEngagementTracking: 'Disabled'
  }
}

resource communication 'Microsoft.Communication/communicationServices@2023-04-01' = {
  name: communicationServiceName
  location: 'global'
  properties: {
    dataLocation: dataLocation
    linkedDomains: [domain.id]
  }
}

output communicationServiceName string = communication.name
output emailServiceName string = email.name
output senderDomain string = domain.properties.mailFromSenderDomain
