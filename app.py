import flask
from flask import request,jsonify
from flask_cors import CORS, cross_origin
import redis, re, ast, json
import settings

app = flask.Flask(__name__)
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'
redis_db = redis.StrictRedis(host=settings.REDIS_HOST,
	port=settings.REDIS_PORT, db=settings.REDIS_DB)

def create_combine(array):
    new_array = []
    length = len(array)
    for i in range(1,length+1):
        for j in range(length-i+1):
            new_array.append(" ".join(array[j:j+i]))
    return new_array

def extract_feedback(feedback):
    delimiters = '.',',','?','!'
    groups = re.split('|'.join(map(re.escape, delimiters)), feedback)
    # new_groups = [w for l in groups for w in create_combine(l)]
    return groups

def cal_freq(table, words, decrease_length, visited_idx):
    length = len(words)
    if decrease_length == length:
        return
    check_smaller = False
    for i in range(decrease_length+1):
        end = i + length - decrease_length
        if i in visited_idx and end-1 in visited_idx:
            continue
        else:
            combine = " ".join(words[i:end])
            freq = table.get(combine, 0)
            if freq > 0:
                table[combine] = freq + 1
                visited_idx.update(range(i,end))
                sub_combines = create_combine(words[i:end])
                for sub in sub_combines[:-1]:
                    sub_freq = table.get(sub, 0)
                    if sub_freq > 0:
                        table[sub] = sub_freq - 1
            else:
                table[combine] = 1
                check_smaller = True
    if check_smaller:
        cal_freq(table, words, decrease_length+1, visited_idx)

def process_keywords(table, groups):
    for g in groups:
        visited_idx = set()
        cal_freq(table, g.strip().split(" "), 0, visited_idx)

@app.route("/add_feedback", methods=["POST"])
@cross_origin()
def add_feedback():
    """
    Get raw data from fibi backend and extract keywords.
    Raw data example: {"data":[{"formId":"5ee89d6128386b1884655530","questionId":"câu hỏi1","answer":"a"},
    {"formId":"5ee89d6128386b1884655530","questionId":"câu hỏi2","answer":"b"}]}
    """
    content = request.get_json(force=True)
    data = content['data']
    for item in data:
        formId = item['formId'] 
        questionId = item['questionId']
        answer = item['answer'].lower() 
        results = redis_db.get(formId+questionId)
        if results is None:
            redis_db.rpush(formId, questionId)
            freq_dict = {}
        else:
            dict_str = results.decode("UTF-8")
            freq_dict = ast.literal_eval(dict_str)
        process_keywords(freq_dict, extract_feedback(answer))
        redis_db.set(formId+questionId, json.dumps(freq_dict))
    data = {"status": True}
    return jsonify(data)

@app.route("/get_word_freq", methods=["GET"])
@cross_origin()
def get_word_freq():
    """
    Return frequency of words in the same question.
    Arguments: 
        - formId: ObjectId String
    """
    formId = request.args.get('formId')
    question_list = redis_db.lrange(formId,0,-1)
    word_freqs = []
    for question in question_list:
        results = redis_db.get(formId+question.decode('UTF-8'))
        dict_str = results.decode("UTF-8")
        freq_dict = ast.literal_eval(dict_str)
        display_dict = {k: v for k, v in freq_dict.items() if v > 1}
        word_freqs.append({question.decode('UTF-8'): display_dict})
    return jsonify(word_freqs)

@app.route("/del_form", methods=["POST"])
@cross_origin()
def del_form():
    """
    Delete the survey data stored and return number of questions is deleted.
    Arguments: 
        - formId: ObjectId String
    """
    formId = request.form.get('formId')
    question_list = redis_db.lrange(formId,0,-1)
    for question in question_list:
        redis_db.delete(formId+question.decode('UTF-8'))
    redis_db.delete(formId)
    return jsonify({"deleted": {formId:len(question_list)}})

if __name__ == "__main__":
   print("* Starting web service...")
   app.run(port=9999,debug=True)