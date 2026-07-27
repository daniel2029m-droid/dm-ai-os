const geminiKey = "AIzaSyDkMs54e1zPfbI3k28rzN10ZksgsFl_qDQ";
fetch(`https://generativelanguage.googleapis.com/v1beta/models?key=${geminiKey}`)
.then(res => res.json())
.then(data => console.log(data.models.map(m => m.name).join(', ')))
.catch(console.error);
