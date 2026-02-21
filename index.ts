/**
 * Parakeet STT Plugin for OpenClaw
 *
 * Provides fast CPU-based speech-to-text using Parakeet TDT INT8 models.
 * Supports V2 (English optimized) and V3 (Multilingual) model selection.
 *
 * The actual transcription is configured via tools.media.audio.models in openclaw.json.
 */

import { Type } from "@sinclair/typebox";

export default function (api: any) {
  api.logger.info("parakeet-stt: plugin loaded");

  // Register a CLI command for checking Parakeet status
  api.registerCommand({
    name: "parakeet:status",
    description: "Check Parakeet STT daemon status",
    async handler() {
      const cfg = api.config.plugins?.entries?.["parakeet-stt"] || {};
      const modelVersion = cfg.modelVersion || "v2";
      const toolsDir = `${process.env.HOME}/.openclaw/tools/parakeet`;
      const modelPath = cfg.modelPath || `${toolsDir}/model`;

      return {
        modelVersion,
        modelPath,
        daemonPath: `${toolsDir}/parakeet-lazy-daemon.py`,
        enabled: cfg.enabled !== false,
        timeout: cfg.timeoutMs || 30000,
        inactivityTimeout: (cfg.inactivityTimeoutMin || 20) + " minutes",
        installCommand: `bash ~/.openclaw/extensions/parakeet-stt/scripts/install.sh ${modelVersion}`
      };
    },
  });

  // Register a CLI command for installing the model
  api.registerCommand({
    name: "parakeet:install",
    description: "Download and install a Parakeet TDT model",
    async handler(args: { version?: string }) {
      const cfg = api.config.plugins?.entries?.["parakeet-stt"] || {};
      const version = args?.version || cfg.modelVersion || "v2";
      const installScript = `${process.env.HOME}/.openclaw/extensions/parakeet-stt/scripts/install.sh`;
      api.logger.info?.(`parakeet-stt: install command called for ${version}`);

      return {
        message: `Run the install script for ${version}:`,
        command: `bash ${installScript} ${version}`,
        hint: "v2 = English optimized, v3 = Multilingual (25 languages)"
      };
    },
  });

  // Register an agent tool for checking transcription status
  api.registerTool(
    {
      name: "parakeet_status",
      description: "Check the status of the Parakeet speech-to-text system",
      parameters: Type.Object({}),
      async execute() {
        const cfg = api.config.plugins?.entries?.["parakeet-stt"] || {};
        const modelVersion = cfg.modelVersion || "v2";
        const modelPath = cfg.modelPath || `${process.env.HOME}/.openclaw/tools/parakeet/model`;

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({
                enabled: cfg.enabled !== false,
                modelVersion,
                modelPath,
                configured: !!cfg.enabled
              }, null, 2)
            }
          ]
        };
      },
    },
    { optional: true }
  );
}
