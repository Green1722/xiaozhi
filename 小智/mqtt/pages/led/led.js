//index.js
//获取应用实例
const app = getApp()
var mqtt = require('../../utils/mqtt.js');

var rex = /^[0-9]+$/;//正则表达式

Page({
  data: {
   
      value:{
        valueR:null,
        valueG:null,
        valueB:null
      },
      topic:"classroom/light/control"
    
    
   
  },

  TopicInput:function(e){
   
    this.setData({
     topic:e.detail.value
    })
  },

  RInput:function(e){
    if(!rex.test(e.detail.value)||e.detail.value<0||e.detail.value>255)
    this.setData({
      'value.valueR':null
    })
    else
    this.setData({
      'value.valueR':parseInt(e.detail.value)
    })
  },

  GInput:function(e){
    if(!rex.test(e.detail.value)||e.detail.value<0||e.detail.value>255)
    this.setData({
      'value.valueG':null
    })
    else
    this.setData({
      'value.valueG':parseInt(e.detail.value)
    })
  },

  BInput:function(e){
    if(!rex.test(e.detail.value)||e.detail.value<0||e.detail.value>255)
    this.setData({
      'value.valueB':null
    })
    else
    this.setData({
      'value.valueB':parseInt(e.detail.value)
    })
  },



  //发送mqtt
  sendmqtt: function() {
    // 构造符合Python服务期望的消息格式
    var message = {
      action: 'brightness', // LED控制视为亮度控制
      timestamp: new Date().toISOString(),
      brightness: Math.round((this.data.value.valueR + this.data.value.valueG + this.data.value.valueB) / 3) // 平均值作为亮度
    };

    // 如果RGB值相同，可能是白色，否则发送RGB值
    if (this.data.value.valueR === this.data.value.valueG && this.data.value.valueG === this.data.value.valueB) {
      message.brightness = this.data.value.valueR;
    } else {
      // 发送RGB值（扩展消息格式）
      message.rgb = {
        r: this.data.value.valueR,
        g: this.data.value.valueG,
        b: this.data.value.valueB
      };
    }

    var payload = JSON.stringify(message);
    app.globalData.client.publish(this.data.topic, payload);
    console.log("LED控制消息已发送:", payload);
  },

})
