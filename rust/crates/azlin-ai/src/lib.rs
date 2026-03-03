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

    // ── ApiRequest serialization tests ──────────────────────────────

    #[test]
    fn test_api_request_serialization() {
        let req = ApiRequest {
            model: "claude-sonnet-4-20250514".to_string(),
            max_tokens: 1024,
            messages: vec![Message {
                role: "user".to_string(),
                content: "Hello".to_string(),
            }],
            system: Some("You are helpful".to_string()),
        };
        let json = serde_json::to_value(&req).unwrap();
        assert_eq!(json["model"], "claude-sonnet-4-20250514");
        assert_eq!(json["max_tokens"], 1024);
        assert_eq!(json["messages"][0]["role"], "user");
        assert_eq!(json["messages"][0]["content"], "Hello");
        assert_eq!(json["system"], "You are helpful");
    }

    #[test]
    fn test_api_request_without_system() {
        let req = ApiRequest {
            model: "claude-sonnet-4-20250514".to_string(),
            max_tokens: 512,
            messages: vec![],
            system: None,
        };
        let json = serde_json::to_value(&req).unwrap();
        assert!(json["system"].is_null());
        assert_eq!(json["max_tokens"], 512);
        assert!(json["messages"].as_array().unwrap().is_empty());
    }

    #[test]
    fn test_api_request_multiple_messages() {
        let req = ApiRequest {
            model: "test-model".to_string(),
            max_tokens: 256,
            messages: vec![
                Message {
                    role: "user".to_string(),
                    content: "First".to_string(),
                },
                Message {
                    role: "assistant".to_string(),
                    content: "Response".to_string(),
                },
                Message {
                    role: "user".to_string(),
                    content: "Follow-up".to_string(),
                },
            ],
            system: None,
        };
        let json = serde_json::to_value(&req).unwrap();
        let msgs = json["messages"].as_array().unwrap();
        assert_eq!(msgs.len(), 3);
        assert_eq!(msgs[1]["role"], "assistant");
    }

    // ── ApiResponse deserialization tests ────────────────────────────

    #[test]
    fn test_api_response_deserialization() {
        let json = r#"{"content": [{"text": "Hello, world!"}]}"#;
        let resp: ApiResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.content.len(), 1);
        assert_eq!(resp.content[0].text.as_deref().unwrap(), "Hello, world!");
    }

    #[test]
    fn test_api_response_empty_content() {
        let json = r#"{"content": []}"#;
        let resp: ApiResponse = serde_json::from_str(json).unwrap();
        assert!(resp.content.is_empty());
    }

    #[test]
    fn test_api_response_multiple_content_blocks() {
        let json = r#"{"content": [{"text": "Part 1"}, {"text": "Part 2"}, {"text": "Part 3"}]}"#;
        let resp: ApiResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.content.len(), 3);
        let joined: String = resp
            .content
            .into_iter()
            .filter_map(|b| b.text)
            .collect::<Vec<_>>()
            .join("");
        assert_eq!(joined, "Part 1Part 2Part 3");
    }

    #[test]
    fn test_api_response_content_block_without_text() {
        let json = r#"{"content": [{"text": null}]}"#;
        let resp: ApiResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.content.len(), 1);
        assert!(resp.content[0].text.is_none());
    }

    #[test]
    fn test_api_response_mixed_content_blocks() {
        let json = r#"{"content": [{"text": "Hello"}, {"text": null}, {"text": " World"}]}"#;
        let resp: ApiResponse = serde_json::from_str(json).unwrap();
        let joined: String = resp
            .content
            .into_iter()
            .filter_map(|b| b.text)
            .collect::<Vec<_>>()
            .join("");
        assert_eq!(joined, "Hello World");
    }

    // ── Message serialization tests ─────────────────────────────────

    #[test]
    fn test_message_serialization() {
        let msg = Message {
            role: "user".to_string(),
            content: "test message".to_string(),
        };
        let json = serde_json::to_value(&msg).unwrap();
        assert_eq!(json["role"], "user");
        assert_eq!(json["content"], "test message");
    }

    #[test]
    fn test_message_with_special_chars() {
        let msg = Message {
            role: "user".to_string(),
            content: "Hello \"world\" with\nnewlines\tand\ttabs".to_string(),
        };
        let json_str = serde_json::to_string(&msg).unwrap();
        let deserialized: serde_json::Value = serde_json::from_str(&json_str).unwrap();
        assert_eq!(
            deserialized["content"],
            "Hello \"world\" with\nnewlines\tand\ttabs"
        );
    }

    // ── Command parsing logic tests ─────────────────────────────────

    #[test]
    fn test_parse_commands_empty_text() {
        let text = "";
        let commands: Vec<String> = text
            .lines()
            .map(|l| l.trim().to_string())
            .filter(|l| !l.is_empty())
            .collect();
        assert!(commands.is_empty());
    }

    #[test]
    fn test_parse_commands_whitespace_only() {
        let text = "  \n  \n\n  ";
        let commands: Vec<String> = text
            .lines()
            .map(|l| l.trim().to_string())
            .filter(|l| !l.is_empty())
            .collect();
        assert!(commands.is_empty());
    }

    #[test]
    fn test_parse_commands_with_leading_trailing_whitespace() {
        let text = "  az vm list  \n  az vm stop  \n";
        let commands: Vec<String> = text
            .lines()
            .map(|l| l.trim().to_string())
            .filter(|l| !l.is_empty())
            .collect();
        assert_eq!(commands.len(), 2);
        assert_eq!(commands[0], "az vm list");
        assert_eq!(commands[1], "az vm stop");
    }

    #[test]
    fn test_parse_commands_single_command() {
        let text = "az vm list --resource-group myRG\n";
        let commands: Vec<String> = text
            .lines()
            .map(|l| l.trim().to_string())
            .filter(|l| !l.is_empty())
            .collect();
        assert_eq!(commands.len(), 1);
        assert_eq!(commands[0], "az vm list --resource-group myRG");
    }

    #[test]
    fn test_parse_commands_with_blank_lines_between() {
        let text = "az vm list\n\n\naz vm stop\n\naz vm start\n";
        let commands: Vec<String> = text
            .lines()
            .map(|l| l.trim().to_string())
            .filter(|l| !l.is_empty())
            .collect();
        assert_eq!(commands.len(), 3);
    }

    // ── Client default model test ───────────────────────────────────

    #[test]
    fn test_client_default_model() {
        let saved = std::env::var("ANTHROPIC_API_KEY").ok();
        std::env::set_var("ANTHROPIC_API_KEY", "test-key");
        let client = AnthropicClient::new().unwrap();
        assert!(
            client.model.contains("claude"),
            "default model should contain 'claude': {}",
            client.model
        );
        assert!(
            client.model.contains("sonnet"),
            "default model should contain 'sonnet': {}",
            client.model
        );
        match saved {
            Some(v) => std::env::set_var("ANTHROPIC_API_KEY", v),
            None => std::env::remove_var("ANTHROPIC_API_KEY"),
        }
    }

    #[test]
    fn test_client_stores_api_key() {
        // Use a direct field check instead of env var manipulation
        // which can race with other tests
        let client = AnthropicClient {
            client: reqwest::Client::new(),
            api_key: "my-secret-key-abc".to_string(),
            model: "claude-sonnet-4-20250514".to_string(),
        };
        assert_eq!(client.api_key, "my-secret-key-abc");
    }

    #[test]
    fn test_client_error_message_mentions_env_var() {
        let saved = std::env::var("ANTHROPIC_API_KEY").ok();
        std::env::remove_var("ANTHROPIC_API_KEY");
        let result = AnthropicClient::new();
        assert!(result.is_err(), "should fail without API key");
        let err_msg = format!("{}", result.err().unwrap());
        assert!(
            err_msg.contains("ANTHROPIC_API_KEY"),
            "error should mention env var: {}",
            err_msg
        );
        if let Some(v) = saved {
            std::env::set_var("ANTHROPIC_API_KEY", v)
        }
    }

    // ── Async method tests (exercise code paths with failures) ──────

    #[tokio::test]
    async fn test_ask_with_invalid_key_returns_error() {
        let saved = std::env::var("ANTHROPIC_API_KEY").ok();
        std::env::set_var("ANTHROPIC_API_KEY", "sk-invalid-test-key");
        let client = AnthropicClient::new().unwrap();
        let result = client.ask("test query", "test context").await;
        // Should fail at HTTP level (401 or network error)
        assert!(result.is_err());
        match saved {
            Some(v) => std::env::set_var("ANTHROPIC_API_KEY", v),
            None => std::env::remove_var("ANTHROPIC_API_KEY"),
        }
    }

    #[tokio::test]
    async fn test_execute_with_invalid_key_returns_error() {
        let saved = std::env::var("ANTHROPIC_API_KEY").ok();
        std::env::set_var("ANTHROPIC_API_KEY", "sk-invalid-test-key");
        let client = AnthropicClient::new().unwrap();
        let result = client.execute("list all VMs").await;
        assert!(result.is_err());
        match saved {
            Some(v) => std::env::set_var("ANTHROPIC_API_KEY", v),
            None => std::env::remove_var("ANTHROPIC_API_KEY"),
        }
    }
}
