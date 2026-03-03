//! azlin-ai: Anthropic Claude API integration for NLP command execution.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

/// Client for the Anthropic Claude API.
pub struct AnthropicClient {
    client: reqwest::Client,
    api_key: String,
    model: String,
}

#[derive(Serialize)]
struct Message {
    role: String,
    content: String,
}

#[derive(Serialize)]
struct ApiRequest {
    model: String,
    max_tokens: u32,
    messages: Vec<Message>,
    system: Option<String>,
}

#[derive(Deserialize)]
struct ApiResponse {
    content: Vec<ContentBlock>,
}

#[derive(Deserialize)]
struct ContentBlock {
    text: Option<String>,
}

impl AnthropicClient {
    /// Create a new client, reading ANTHROPIC_API_KEY from the environment.
    pub fn new() -> Result<Self> {
        let api_key = std::env::var("ANTHROPIC_API_KEY")
            .context("ANTHROPIC_API_KEY environment variable not set")?;
        Ok(Self {
            client: reqwest::Client::new(),
            api_key,
            model: "claude-sonnet-4-20250514".to_string(),
        })
    }

    /// Send a natural-language query with optional context to Claude.
    pub async fn ask(&self, query: &str, context: &str) -> Result<String> {
        let system = format!(
            "You are an Azure VM fleet management assistant. \
             Answer questions about the fleet based on the provided context.\n\n\
             Context:\n{context}"
        );

        let request = ApiRequest {
            model: self.model.clone(),
            max_tokens: 1024,
            messages: vec![Message {
                role: "user".to_string(),
                content: query.to_string(),
            }],
            system: Some(system),
        };

        let resp = self
            .client
            .post("https://api.anthropic.com/v1/messages")
            .header("x-api-key", &self.api_key)
            .header("anthropic-version", "2023-06-01")
            .header("content-type", "application/json")
            .json(&request)
            .send()
            .await
            .context("Failed to send request to Anthropic API")?;

        let status = resp.status();
        if !status.is_success() {
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("Anthropic API error ({}): {}", status, body);
        }

        let api_resp: ApiResponse = resp
            .json()
            .await
            .context("Failed to parse Anthropic API response")?;

        let text = api_resp
            .content
            .into_iter()
            .filter_map(|b| b.text)
            .collect::<Vec<_>>()
            .join("");

        Ok(text)
    }

    /// Parse a natural-language instruction into a list of az CLI commands.
    pub async fn execute(&self, instruction: &str) -> Result<Vec<String>> {
        let system = "You are an Azure CLI command generator. \
             Given a natural language instruction about Azure VMs, \
             output ONLY the az CLI commands needed, one per line. \
             Do not include any explanation or markdown formatting."
            .to_string();

        let request = ApiRequest {
            model: self.model.clone(),
            max_tokens: 1024,
            messages: vec![Message {
                role: "user".to_string(),
                content: instruction.to_string(),
            }],
            system: Some(system),
        };

        let resp = self
            .client
            .post("https://api.anthropic.com/v1/messages")
            .header("x-api-key", &self.api_key)
            .header("anthropic-version", "2023-06-01")
            .header("content-type", "application/json")
            .json(&request)
            .send()
            .await
            .context("Failed to send request to Anthropic API")?;

        let status = resp.status();
        if !status.is_success() {
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("Anthropic API error ({}): {}", status, body);
        }

        let api_resp: ApiResponse = resp
            .json()
            .await
            .context("Failed to parse Anthropic API response")?;

        let text = api_resp
            .content
            .into_iter()
            .filter_map(|b| b.text)
            .collect::<Vec<_>>()
            .join("");

        let commands: Vec<String> = text
            .lines()
            .map(|l| l.trim().to_string())
            .filter(|l| !l.is_empty())
            .collect();

        Ok(commands)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // These tests modify env vars and must run serially.
    // We use a single test to avoid race conditions.
    #[test]
    fn test_new_requires_and_reads_api_key() {
        let saved = std::env::var("ANTHROPIC_API_KEY").ok();

        // Without key → error
        std::env::remove_var("ANTHROPIC_API_KEY");
        let result = AnthropicClient::new();
        assert!(result.is_err());

        // With key → success
        std::env::set_var("ANTHROPIC_API_KEY", "test-key-12345");
        let client = AnthropicClient::new().unwrap();
        assert_eq!(client.api_key, "test-key-12345");
        assert!(client.model.contains("claude"));

        // Restore
        match saved {
            Some(v) => std::env::set_var("ANTHROPIC_API_KEY", v),
            None => std::env::remove_var("ANTHROPIC_API_KEY"),
        }
    }

    #[test]
    fn test_parse_commands_from_text() {
        let text =
            "az vm list --resource-group myRG\naz vm start --name myVM --resource-group myRG\n";
        let commands: Vec<String> = text
            .lines()
            .map(|l| l.trim().to_string())
            .filter(|l| !l.is_empty())
            .collect();
        assert_eq!(commands.len(), 2);
        assert!(commands[0].starts_with("az vm list"));
        assert!(commands[1].starts_with("az vm start"));
    }
}
