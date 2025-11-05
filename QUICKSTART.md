# ⚡ Quick Start Guide

## 🚀 Get Running in 5 Minutes

### Step 1: Clone and Navigate
```bash
git clone https://github.com/yourusername/NaturalSQL-AI.git
cd NaturalSQL-AI
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Create Sample Database
```bash
python sqlite.py
```

### Step 4: Get Your Groq API Key
1. Visit https://console.groq.com/
2. Sign up or log in
3. Navigate to API Keys section
4. Create a new API key
5. Copy the key

### Step 5: Run the Application
```bash
streamlit run app.py
```

### Step 6: Configure in Browser
1. Open http://localhost:8501
2. Select "Use SQLLite 3 Database - Student.db"
3. Paste your Groq API key in the sidebar
4. Start chatting!

---

## 💬 Try These Queries

**Simple:**
```
How many students are in the database?
```

**Filtering:**
```
Show me all students with marks greater than 85
```

**Aggregation:**
```
What is the average marks by class?
```

**Grouping:**
```
Count students by section
```

**Sorting:**
```
Who has the highest marks?
```

---

## 🔧 Troubleshooting

### Issue: "Module not found"
**Solution:** 
```bash
pip install -r requirements.txt --upgrade
```

### Issue: "Database not found"
**Solution:**
```bash
python sqlite.py
```

### Issue: "API key invalid"
**Solution:** 
- Check your Groq API key at https://console.groq.com/
- Make sure you copied the entire key
- Try generating a new key

### Issue: "Port already in use"
**Solution:**
```bash
streamlit run app.py --server.port 8502
```

---

## 🎯 Next Steps

1. ✅ **Try different models** - Switch between Llama3-8b, Llama3-70b, Mixtral
2. ✅ **Adjust temperature** - Experiment with creativity settings
3. ✅ **View schema** - Use the database schema viewer
4. ✅ **Connect MySQL** - Try with your own database
5. ✅ **Check history** - Review your query history in sidebar

---

## 📚 Learn More

- **Full Documentation**: See README.md
- **Configuration Options**: Check config.py
- **Advanced Setup**: Review setup.py
- **Code Enhancements**: See ENHANCEMENTS.md

---

## 🆘 Need Help?

- **GitHub Issues**: [Create an issue](https://github.com/yourusername/NaturalSQL-AI/issues)
- **Documentation**: Check README.md
- **Email**: your.email@example.com

---

**Happy Querying! 🎉**
