# 🤝 Contributing to NaturalSQL-AI

First off, thank you for considering contributing to NaturalSQL-AI! It's people like you that make this project better for everyone.

## 🌟 How Can I Contribute?

### Reporting Bugs 🐛

Before creating bug reports, please check existing issues to avoid duplicates.

**When reporting a bug, include:**
- **Description**: Clear description of the problem
- **Steps to Reproduce**: Detailed steps to recreate the issue
- **Expected Behavior**: What you expected to happen
- **Actual Behavior**: What actually happened
- **Environment**: OS, Python version, package versions
- **Screenshots**: If applicable

**Example:**
```
**Bug**: Query fails with special characters

**Steps to Reproduce:**
1. Enter query: "Show students with names containing 'O'Brien'"
2. Click send
3. See error

**Expected**: Results showing students with O'Brien
**Actual**: ParseError exception

**Environment**: Windows 10, Python 3.9, Streamlit 1.28
```

### Suggesting Enhancements 💡

Enhancement suggestions are tracked as GitHub issues.

**When suggesting an enhancement, include:**
- **Use Case**: Why would this be useful?
- **Proposed Solution**: How would it work?
- **Alternatives**: Other approaches you've considered
- **Examples**: Similar features in other tools

### Pull Requests 🔀

**Good Pull Requests include:**
- Clear description of changes
- Tests (if applicable)
- Updated documentation
- Follows coding standards
- Addresses a specific issue

## 🚀 Development Setup

### 1. Fork and Clone
```bash
# Fork on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/NaturalSQL-AI.git
cd NaturalSQL-AI
```

### 2. Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Create a Branch
```bash
git checkout -b feature/amazing-feature
# or
git checkout -b bugfix/issue-123
```

### 5. Make Your Changes
- Write clean, commented code
- Follow PEP 8 style guidelines
- Test your changes thoroughly

### 6. Test Locally
```bash
streamlit run app.py
```

### 7. Commit Your Changes
```bash
git add .
git commit -m "Add: Brief description of changes"
```

**Commit Message Format:**
- `Add: New feature description`
- `Fix: Bug fix description`
- `Update: Changes to existing feature`
- `Docs: Documentation updates`
- `Refactor: Code restructuring`
- `Test: Adding or updating tests`

### 8. Push and Create PR
```bash
git push origin feature/amazing-feature
```

Then create a Pull Request on GitHub.

## 📝 Coding Standards

### Python Style Guide

**Follow PEP 8:**
```python
# Good
def calculate_average_marks(student_list: List[Dict]) -> float:
    """Calculate average marks for a list of students.
    
    Args:
        student_list: List of student dictionaries
        
    Returns:
        Average marks as float
    """
    total = sum(student['marks'] for student in student_list)
    return total / len(student_list)

# Bad
def calc_avg(l):
    t=sum(s['marks'] for s in l)
    return t/len(l)
```

**Use Type Hints:**
```python
from typing import Optional, List, Dict

def connect_database(
    uri: str,
    host: Optional[str] = None,
    user: Optional[str] = None
) -> SQLDatabase:
    pass
```

**Add Docstrings:**
```python
def process_query(query: str, db: SQLDatabase) -> Dict[str, Any]:
    """
    Process a natural language query against the database.
    
    Args:
        query: Natural language question from user
        db: SQLDatabase instance to query against
        
    Returns:
        Dictionary containing query results and metadata
        
    Raises:
        ValueError: If query is empty or invalid
        DatabaseError: If database connection fails
    """
    pass
```

### Code Organization

**Keep functions focused:**
```python
# Good - Single responsibility
def validate_api_key(key: str) -> bool:
    """Validate Groq API key format."""
    return len(key) > 20 and key.startswith('gsk_')

def connect_to_database(config: dict) -> SQLDatabase:
    """Establish database connection."""
    return SQLDatabase(create_engine(config['uri']))

# Bad - Multiple responsibilities
def setup_everything(api_key, db_uri):
    # validates, connects, initializes...
    pass
```

**Use configuration files:**
```python
# Good
from config import AGENT_CONFIG, DB_CONFIG

agent = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    **AGENT_CONFIG
)

# Bad
agent = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    verbose=True,
    max_iterations=15,
    handle_parsing_errors=True
)
```

## 🧪 Testing Guidelines

### Manual Testing Checklist

Before submitting a PR, test:

- [ ] SQLite connection works
- [ ] MySQL connection works (if applicable)
- [ ] Sample queries execute successfully
- [ ] Error handling shows user-friendly messages
- [ ] UI elements render correctly
- [ ] Schema viewer displays tables
- [ ] Query history tracks correctly
- [ ] Model switching works
- [ ] Temperature adjustment affects responses
- [ ] App works on fresh Python environment

### Future: Automated Tests

```python
# Example test structure (for future implementation)
import pytest
from app import configure_db, validate_query

def test_sqlite_connection():
    """Test SQLite database connection."""
    db = configure_db("USE_LOCALDB")
    assert db is not None
    assert len(db.get_usable_table_names()) > 0

def test_query_validation():
    """Test query validation logic."""
    valid_query = "Show all students"
    invalid_query = ""
    
    assert validate_query(valid_query) == True
    assert validate_query(invalid_query) == False
```

## 📚 Documentation Standards

### Code Comments

```python
# Good comments - Explain WHY
# Cache database connections to reduce overhead and improve performance
@st.cache_resource(ttl="2h")
def configure_db(db_uri: str) -> SQLDatabase:
    pass

# Bad comments - Explain WHAT (code already shows this)
# Create a database connection
def configure_db(db_uri):
    pass
```

### README Updates

When adding features, update:
- [ ] Features section
- [ ] Usage examples
- [ ] Configuration options
- [ ] Dependencies (if added)
- [ ] Screenshots (if UI changed)

## 🎯 Priority Areas for Contribution

### High Priority 🔴
- PostgreSQL database support
- Export query results to CSV/Excel
- Data visualization (charts/graphs)
- Unit test framework
- Docker containerization

### Medium Priority 🟡
- Dark mode theme
- Query optimization suggestions
- Voice input support
- Multi-language UI
- Enhanced error messages

### Low Priority 🟢
- Query scheduling
- User authentication
- API endpoint
- Custom themes
- Mobile responsive design

## ✅ Pull Request Checklist

Before submitting your PR:

- [ ] Code follows PEP 8 style guidelines
- [ ] All functions have docstrings
- [ ] Type hints added where appropriate
- [ ] Comments explain complex logic
- [ ] Tested on local environment
- [ ] No API keys or secrets in code
- [ ] Requirements.txt updated (if needed)
- [ ] README updated (if needed)
- [ ] ENHANCEMENTS.md updated (if new feature)
- [ ] Commit messages are descriptive
- [ ] Branch is up-to-date with main

## 🏆 Recognition

Contributors will be:
- Listed in README.md
- Mentioned in release notes
- Credited in CONTRIBUTORS.md
- Given shout-out on LinkedIn (if desired)

## 📞 Questions?

- **GitHub Issues**: For bugs and features
- **GitHub Discussions**: For questions and ideas
- **Email**: your.email@example.com

## 📜 Code of Conduct

### Our Pledge

We pledge to make participation in our project a harassment-free experience for everyone, regardless of:
- Age, body size, disability
- Ethnicity, gender identity
- Experience level
- Nationality, personal appearance
- Race, religion
- Sexual identity and orientation

### Our Standards

**Positive behavior includes:**
- Using welcoming and inclusive language
- Being respectful of differing viewpoints
- Gracefully accepting constructive criticism
- Focusing on what's best for the community
- Showing empathy towards others

**Unacceptable behavior includes:**
- Trolling, insulting/derogatory comments
- Public or private harassment
- Publishing others' private information
- Other conduct considered inappropriate

## 🎉 Thank You!

Every contribution, no matter how small, makes a difference. Whether you're:
- Fixing a typo in documentation
- Reporting a bug
- Suggesting a feature
- Submitting code

**You're making NaturalSQL-AI better for everyone! 🙏**

---

**Happy Contributing! 🚀**
