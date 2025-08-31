from flaskws import app

if __name__ == "__main__":
    try:
        app.run(debug=False, threaded=True)
    except:
        raise
