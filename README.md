# storyOS - Interactive Narrative Chat

A Streamlit-powered interactive storytelling application featuring scenario-defined Dungeon Masters and comprehensive Chronicle memory system.

## Features

### 🎭 Scenario-Defined DM System
- **Flexible DM Behavior**: Each scenario defines its own DM personality, tone, pacing, and interaction style
- **Dynamic Content**: Stories adapt based on scenario-specific mechanics and safety constraints
- **Multiple Scenarios**: Choose from various pre-built scenarios or create your own

### 📜 Chronicle Memory & Archive System
- **Persistent Timeline**: Automatically tracks all story events with rich metadata
- **Character Summaries**: Dynamic character development and relationship tracking
- **World State**: Maintains setting, rules, and ongoing plot threads
- **Current Scenario**: Real-time snapshot for seamless story continuation

### 🔒 Mature Content Handling
- **Flexible Content Policies**: Support for SFW, reference-based, and inline content modes
- **Encrypted Vault System**: Secure storage of mature content with AES-256-GCM encryption
- **Age Verification**: Configurable content gates based on user verification
- **Scenario Safety Locks**: Scenarios can enforce their own content boundaries

### 💬 Rich Chat Interface
- **Streaming Responses**: Real-time story generation with visual feedback
- **Suggested Actions**: Context-aware action buttons for easy interaction
- **Export Options**: Save chronicles and chat logs in multiple formats
- **Session Management**: Save/load games with full state preservation

## Quick Start

### Prerequisites
- Python 3.8 or higher
- X.AI API key (for Grok) or OpenAI API key (or compatible LLM service)

### Installation

1. Clone or download the storyOS directory
2. Install dependencies:
   ```bash
   cd storyos
   pip install -r requirements.txt
   ```

3. Configure your environment:
   ```bash
   # Option 1: Environment variables
   cp .env.example .env
   # Edit .env with your API keys
   
   # Option 2: Streamlit secrets (recommended)
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   # Edit secrets.toml with your API keys
   ```

4. Run the application:
   ```bash
   streamlit run app.py
   ```

### Environment Variables

Configure these in `.env` or `.streamlit/secrets.toml`:

| Variable | Description | Required |
|----------|-------------|----------|
| `XAI_API_KEY` | Your X.AI API key (for Grok) | Yes* |
| `OPENAI_API_KEY` | Your OpenAI API key (alternative) | Yes* |
| `XAI_BASE_URL` | X.AI API base URL (default: https://api.x.ai/v1) | No |
| `OPENAI_BASE_URL` | OpenAI API base URL (default: https://api.openai.com/v1) | No |
| `DEFAULT_MODEL` | LLM model to use (default: grok-beta) | No |
| `CHRONICLE_ENCRYPTION_KEY` | 32-byte hex key for mature content encryption | No** |

*Either XAI_API_KEY or OPENAI_API_KEY is required
**Required only if using mature content with encryption

### Getting X.AI API Key
1. Sign up at [x.ai](https://x.ai/)
2. Navigate to your API settings
3. Generate a new API key
4. Copy the key to your configuration

### Generate Encryption Key

```bash
python -c \"import secrets; print(secrets.token_hex(32))\"
```

## Usage

1. **Start the App**: Run `streamlit run app.py`
2. **Select Scenario**: Choose from available scenarios in the sidebar
3. **Begin Story**: Click \"Start Story\" to initialize the game
4. **Interact**: Type responses or use suggested action buttons
5. **Save/Export**: Use sidebar controls to save progress or export chronicles

## Scenario Authoring Guide

### Scenario Structure

Scenarios are defined in JSON or YAML format in the `scenarios/packs/` directory. Here's the basic structure:

```json
{
  \"id\": \"unique_scenario_id\",
  \"name\": \"Human Readable Name\",
  \"description\": \"Brief description for users\",
  \"version\": \"1.0.0\",
  \"setting\": {
    \"world\": \"Setting description\",
    \"location\": \"Starting location\",
    \"time_period\": \"When the story takes place\"
  },
  \"dm_behavior\": {
    \"tone\": \"DM's narrative voice\",
    \"pacing\": \"slow_burn|moderate|dynamic|fast_paced\",
    \"description_style\": \"How scenes are described\",
    \"interaction_style\": \"How NPCs behave\",
    \"special_instructions\": [\"Additional DM guidelines\"]
  },
  \"safety\": {
    \"sfw_lock\": false,
    \"content_boundaries\": [\"Content to avoid\"],
    \"trigger_warnings\": [\"Potential triggers\"],
    \"age_rating\": \"teen|adult\"
  },
  \"mechanics\": {
    \"time_advancement\": \"flexible|real_time|scene_based\",
    \"consequence_system\": \"grades_stress_relationships\",
    \"choice_structure\": \"open_ended\"
  },
  \"initial_state\": {
    \"current_location\": \"Starting location\",
    \"current_time\": \"ISO 8601 timestamp\",
    \"protagonist\": {
      \"name\": \"Character name\",
      \"role\": \"Character role\",
      \"current_status\": \"Starting condition\",
      \"traits\": [\"personality traits\"],
      \"inventory\": [\"starting items\"],
      \"goals\": [\"character objectives\"]
    },
    \"npcs\": {},
    \"academic_status\": {},
    \"stress_level\": 50,
    \"energy_level\": 100,
    \"mood\": \"starting mood\"
  }
}
```

### DM Behavior Configuration

The `dm_behavior` section controls how the AI Dungeon Master responds:

- **tone**: The narrative voice (\"warm and encouraging\", \"mysterious\", \"humorous\")
- **pacing**: How quickly the story moves
  - `slow_burn`: Detailed, contemplative scenes
  - `moderate`: Balanced pacing with good detail
  - `dynamic`: Quick scene changes, action-focused
  - `fast_paced`: Rapid progression, less description
- **description_style**: Level of detail (\"concise\", \"detailed\", \"atmospheric\")
- **interaction_style**: NPC behavior (\"realistic\", \"theatrical\", \"formal\")
- **special_instructions**: Additional guidelines specific to your scenario

### Safety and Content Control

Configure content boundaries and safety features:

```json
\"safety\": {
  \"sfw_lock\": true,           // Forces SFW mode regardless of user settings
  \"content_boundaries\": [      // Content the DM should avoid
    \"graphic violence\",
    \"explicit content\"
  ],
  \"trigger_warnings\": [        // Warn users about potential triggers
    \"academic stress\",
    \"social anxiety\"
  ],
  \"age_rating\": \"teen\"       // Minimum recommended age
}
```

### Mechanics Configuration

Control how the game systems work:

```json
\"mechanics\": {
  \"time_advancement\": \"flexible\",     // How time progresses
  \"consequence_system\": \"grades_stress_relationships\", // What gets tracked
  \"choice_structure\": \"open_ended\",   // How choices are presented
  \"skill_checks\": false,               // Whether to use dice rolls
  \"inventory_management\": true         // Whether to track items
}
```

### Example: Creating a New Scenario

1. Copy the template from `scenarios/schema.py`
2. Customize the fields for your story
3. Save as `.json` or `.yaml` in `scenarios/packs/`
4. Test with the scenario validator
5. Restart the app to load your new scenario

### Validation

The app automatically validates scenarios on startup. Common validation errors:

- **Missing required fields**: Ensure all required fields are present
- **Invalid enum values**: Check that pacing, age_rating, etc. use valid options
- **Malformed timestamps**: Use ISO 8601 format for dates and times
- **Invalid character data**: Ensure protagonist and NPCs have required fields

## Chronicle Format & Memory System

### Chronicle Structure

The Chronicle is a comprehensive record of each story session:

```json
{
  \"chronicle_id\": \"unique identifier\",
  \"session_id\": \"session identifier\",
  \"scenario_id\": \"source scenario\",
  \"created_at\": \"ISO timestamp\",
  \"updated_at\": \"ISO timestamp\",
  \"version\": \"1.0.0\",
  \"timeline\": { \"phases\": [...] },
  \"characters\": { \"name\": {...} },
  \"world\": { \"setting\": [...] },
  \"current\": { \"location\": \"...\", \"time\": \"...\" },
  \"indexes\": { \"by_character\": {}, \"by_tag\": {} },
  \"policy\": { \"sfw_mode\": true, \"mature_handling\": \"redact\" }
}
```

### Timeline Events

Each story event is captured with rich metadata:

- **Event Details**: Title, timestamp, location, participants
- **Actions & Outcomes**: Player actions and DM responses
- **Consequences**: What changed as a result
- **Tags**: Categorization for easy searching
- **Mature Content Handling**: Automatic content filtering and vault storage

### Character Tracking

Dynamic character summaries that evolve with the story:

- **Current Status**: Up-to-date character condition
- **Relationships**: Tracked with status and numerical scores
- **Development**: Goals, recent changes, and growth
- **Academic Progress**: GPA, courses, and academic standing

### Memory Compression

The system automatically compresses old events to manage memory:

- **Recent Events**: Full detail for the last 50 events per phase
- **Historical Events**: Summarized while preserving key plot points
- **Character Summaries**: Always current, with recent changes highlighted
- **Search Indexes**: Fast lookup by character, tag, or content

## Architecture

### Project Structure
```
storyos/
├── app.py                    # Main Streamlit application
├── dm/
│   ├── engine.py            # Game engine and turn processing
│   ├── prompting.py         # LLM prompt construction
│   └── models.py            # Pydantic data models
├── scenarios/
│   ├── schema.py            # Scenario validation schema
│   ├── registry.py          # Scenario loading and management
│   └── packs/               # Scenario definition files
├── memory/
│   └── chronicle.py         # Chronicle memory system
├── services/
│   ├── llm.py              # LLM service abstraction
│   ├── image.py            # Image generation (optional)
│   └── audio.py            # Text-to-speech (optional)
└── data/                    # Saved games and chronicles
```

### Core Components

1. **Game Engine** (`dm/engine.py`): Orchestrates turn processing, state management, and chronicle updates
2. **Chronicle Manager** (`memory/chronicle.py`): Handles persistent story memory with compression and encryption
3. **Scenario Registry** (`scenarios/registry.py`): Loads, validates, and manages story scenarios
4. **LLM Service** (`services/llm.py`): Abstracts LLM provider details and handles response processing
5. **Streamlit App** (`app.py`): User interface with chat, controls, and scenario selection

### Data Flow

1. **User Input** → Chat interface captures player message
2. **Context Building** → Engine assembles scenario + state + chronicle context  
3. **LLM Generation** → Service sends prompt and receives structured response
4. **State Updates** → Engine applies changes and validates constraints
5. **Chronicle Updates** → Manager records events, updates characters/world state
6. **UI Updates** → Interface displays response and updates sidebar info

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest

# Run tests
pytest tests/
```

### Adding New Features

1. **New Scenario Fields**: Update `scenarios/schema.py` with validation
2. **New Game Mechanics**: Extend `dm/engine.py` constraint application
3. **New Content Handling**: Modify `memory/chronicle.py` processing pipeline
4. **New UI Elements**: Add to `app.py` with proper state management

### Custom LLM Providers

The LLM service supports any OpenAI-compatible API:

```python
# Example: Using a different provider
llm_service = LLMService(
    api_key=\"your_key\",
    base_url=\"https://api.your-provider.com/v1\",
    default_model=\"your-model\"
)
```

## Troubleshooting

### Common Issues

**\"OpenAI API key not found\"**
- Ensure your `.env` or `secrets.toml` file contains a valid `OPENAI_API_KEY`
- Check that the file is in the correct location and properly formatted

**\"No scenarios found\"**
- Verify scenario files exist in `scenarios/packs/`
- Check scenario validation with the \"Test Connection\" button
- Review logs for specific validation errors

**\"Connection failed\"**
- Verify your API key is correct and has sufficient credits
- Check the `OPENAI_BASE_URL` if using a custom provider
- Ensure your network allows connections to the LLM service

**Game state corruption**
- Use \"New Game\" button to reset session state
- Check for validation errors in the console logs
- Verify scenario initial_state is properly formatted

### Performance Optimization

- **Memory Usage**: Chronicles compress automatically, but manual compression is available
- **Response Speed**: Adjust `max_tokens` and `temperature` in LLM service calls
- **Storage**: Clean old saves from `data/saves/` periodically

## Contributing

### Scenario Contributions

We welcome new scenarios! Please:

1. Follow the scenario schema exactly
2. Test thoroughly with the validation system
3. Include appropriate safety constraints and age ratings
4. Provide clear, engaging descriptions

### Code Contributions

1. Maintain existing code style and patterns
2. Add appropriate error handling and logging
3. Update documentation for new features
4. Test with multiple scenarios before submitting

## License

This project is provided as-is for educational and research purposes. Please ensure compliance with your chosen LLM provider's terms of service.

## Support

For issues, questions, or contributions:

1. Check the troubleshooting section above
2. Review the scenario authoring guide for content issues  
3. Examine console logs for technical problems
4. Test with the \"Campus Freshman\" scenario to verify basic functionality

---

**Happy Storytelling!** 📚✨