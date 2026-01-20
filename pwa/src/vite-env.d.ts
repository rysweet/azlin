/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AZURE_TENANT_ID: string
  readonly VITE_AZURE_CLIENT_ID: string
  readonly VITE_AZURE_SUBSCRIPTION_ID: string
  readonly VITE_AZURE_REDIRECT_URI?: string
  readonly VITE_AZURE_RESOURCE_GROUP?: string
  readonly DEV: boolean
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
