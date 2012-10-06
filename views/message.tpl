<head>
    <title>{{header}}</title>
    <link type="text/css" href="/static/css/style.css" rel="Stylesheet" />	
</head>
<body>
    <h1>{{header}}</h1>
    <p>{{message}}</p>
    <div class="footer">
    <a href="/">Back</a>
    % if username != None:
    <br/>
    <a href="/auth/logout">Logout</a> {{username}}
    %end
    </div>
</body>
