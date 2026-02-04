# CloudFormation MCP Server - Documentation

This directory contains comprehensive documentation for the CloudFormation MCP Server project.

## Documents

### 1. [Blog Post](./BLOG_POST.md)
**Audience**: AWS developers, architects, and AI enthusiasts  
**Format**: Technical blog post following AWS blog guidelines  
**Length**: ~4,000 words

A comprehensive blog post explaining:
- **What**: An AI-powered CloudFormation generator
- **Why**: Simplifies infrastructure design with AI
- **How**: Built with Amazon Bedrock AgentCore and MCP

**Sections**:
- Introduction and problem statement
- Model Context Protocol (MCP) overview
- Amazon Bedrock AgentCore Runtime benefits
- Solution architecture with detailed diagrams
- Step-by-step walkthrough of how it works
- Key technical decisions and rationale
- Implementation highlights with code examples
- Deployment process
- Cost analysis
- Lessons learned
- Future enhancements
- Conclusion and resources

**Best for**: Understanding the complete solution and its architecture

---

### 2. [Workshop](./WORKSHOP.md)
**Audience**: Developers wanting hands-on experience  
**Format**: Self-paced workshop following AWS workshop guidelines  
**Duration**: 2-3 hours  
**Level**: 300 (Advanced)

A hands-on workshop teaching:
- Building MCP servers with FastMCP
- Deploying to Amazon Bedrock AgentCore Runtime
- Using Kiro AI IDE for accelerated development
- Integrating Claude Sonnet 4.5 via Bedrock
- Creating WebSocket backends
- Building modern web UIs

**Modules**:
0. Workshop Setup (15 min)
1. Understanding Kiro's AI-Assisted Development (20 min)
2. Building Your First MCP Server (30 min)
3. Adding CloudFormation Generation (40 min)
4. Deploying to AgentCore Runtime (30 min)
5. Adding Professional Diagrams (30 min)
6. Building the WebSocket Backend (25 min)
7. Building the Frontend UI (25 min)
8. Using Kiro Specs for Feature Development (20 min)
9. Advanced Features with Kiro Powers (15 min)
10. Monitoring and Observability (15 min)
11. Cleanup (10 min)

**Best for**: Learning by doing with step-by-step instructions

---

### 3. [Kiro Build Guide](./KIRO_BUILD_GUIDE.md)
**Audience**: Kiro AI IDE users  
**Format**: Case study and development guide  
**Focus**: How Kiro accelerated this project

A detailed guide showing:
- How Kiro AI IDE was used throughout development
- Steering files for project-specific guidance
- Kiro Powers for AWS integration
- Autopilot mode for complex features
- Development workflow and patterns
- Time savings comparison (8 hours vs 40+ hours)

**Sections**:
- Project stats and overview
- Kiro features used (steering, powers, chat, autopilot)
- Phase-by-phase development workflow
- Key techniques and patterns
- Steering file best practices
- Power usage patterns
- Lessons learned
- With vs without Kiro comparison

**Best for**: Understanding how to use Kiro effectively for AI agent development

---

## Quick Start

### For Readers
Start with the [Blog Post](./BLOG_POST.md) to understand the solution architecture and implementation.

### For Builders
Follow the [Workshop](./WORKSHOP.md) for hands-on experience building the solution from scratch.

### For Kiro Users
Read the [Kiro Build Guide](./KIRO_BUILD_GUIDE.md) to learn how Kiro accelerated this project and apply the patterns to your own work.

## Document Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                        Blog Post                             │
│  • What, Why, How                                           │
│  • Architecture deep dive                                   │
│  • Technical decisions                                      │
│  • Implementation highlights                                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ References
                     │
┌────────────────────▼────────────────────────────────────────┐
│                       Workshop                               │
│  • Hands-on modules                                         │
│  • Step-by-step instructions                                │
│  • Code examples                                            │
│  • Testing and deployment                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ Demonstrates
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   Kiro Build Guide                           │
│  • Development workflow                                     │
│  • Kiro features used                                       │
│  • Time savings analysis                                    │
│  • Best practices                                           │
└──────────────────────────────────────────────────────────────┘
```

## Key Concepts Covered

### Amazon Bedrock AgentCore Runtime
- Serverless platform for hosting MCP servers
- Auto-scaling and session management
- Built-in IAM authentication
- CloudWatch and X-Ray observability

### Model Context Protocol (MCP)
- Open standard for AI tool integration
- Standardized tool discovery and invocation
- Type-safe parameter validation
- Streaming support

### Kiro AI IDE
- AI-assisted development environment
- Steering files for project guidance
- Powers for service integration
- Autopilot mode for autonomous coding
- Specs for structured feature development

### Architecture Patterns
- WebSocket for real-time AI interactions
- Async Lambda processing
- SigV4 authentication for AWS services
- Container deployment for system dependencies
- Stateless MCP server design

## Additional Resources

### Project Files
- [Main README](../README.md) - Project overview and quick start
- [Deployment Status](../FINAL_DEPLOYMENT.md) - Current deployment details
- [MCP Server Code](../mcp_server.py) - Implementation
- [WebSocket Infrastructure](../deploy/websocket-infrastructure.yaml) - Backend CloudFormation

### External Links
- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [Kiro AI IDE](https://kiro.dev)
- [FastMCP Framework](https://github.com/jlowin/fastmcp)
- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)

## Contributing

Found an issue or have a suggestion? Please:
1. Check existing documentation
2. Review the [Blog Post](./BLOG_POST.md) for architecture details
3. Try the [Workshop](./WORKSHOP.md) for hands-on learning
4. Consult the [Kiro Build Guide](./KIRO_BUILD_GUIDE.md) for development patterns

## License

This documentation is part of the CloudFormation MCP Server project and is available under the MIT License.

---

**Last Updated**: February 3, 2026  
**Version**: 1.0  
**Status**: Complete
